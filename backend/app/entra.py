"""Tenant-pinned Microsoft OpenID Connect with explicitly provisioned identities."""

import base64
import hashlib
import os
import secrets
from datetime import timedelta
from functools import lru_cache
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_db, now
from .models import Audit, Credential, EntraConnection, EntraFlow, EntraIdentity, User
from .security import digest, issue, require_admin

router = APIRouter(prefix="/api")
COOKIE = "rsh_entra_flow"
CALLBACK = "/api/auth/entra/callback"


def cipher():
    try:
        return Fernet(os.environ["SSO_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError):
        raise HTTPException(503, "SSO encryption key is not configured on the server") from None


def origin():
    return os.getenv("APP_ORIGIN", "http://localhost:5173").rstrip("/")


def secure():
    return os.getenv("COOKIE_SECURE", "false").lower() == "true"


class ConnectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    tenant_id: UUID
    client_id: UUID
    client_secret: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool = False


class IdentityInput(BaseModel):
    object_id: UUID
    user_id: int


def connection_dict(c):
    return {
        "id": c.id,
        "name": c.name,
        "tenant_id": c.tenant_id,
        "client_id": c.client_id,
        "enabled": c.enabled,
        "has_secret": bool(c.secret),
    }


def revoke(db, user_ids):
    db.execute(delete(Credential).where(Credential.kind == "sso", Credential.user_id.in_(user_ids)))


@router.get("/admin/sso")
def configuration(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        cipher()
        ready = True
    except HTTPException:
        ready = False
    return {
        "server_ready": ready,
        "redirect_uri": origin() + CALLBACK,
        "connections": [
            connection_dict(c)
            for c in db.scalars(select(EntraConnection).order_by(EntraConnection.name))
        ],
        "identities": [
            {"connection_id": i.connection_id, "object_id": i.object_id, "user_id": i.user_id}
            for i in db.scalars(select(EntraIdentity))
        ],
    }


@router.post("/admin/sso", status_code=201)
def create_connection(
    data: ConnectionInput, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    if not data.client_secret or not data.name.strip():
        raise HTTPException(422, "A name and client secret are required")
    c = EntraConnection(
        name=data.name.strip(),
        tenant_id=str(data.tenant_id),
        client_id=str(data.client_id),
        secret=cipher().encrypt(data.client_secret.encode()).decode(),
        enabled=data.enabled,
    )
    db.add(c)
    db.flush()
    db.add(
        Audit(actor_id=user.id, action="sso_connection_created", details={"connection_id": c.id})
    )
    db.commit()
    return connection_dict(c)


@router.put("/admin/sso/{connection_id}")
def update_connection(
    connection_id: int,
    data: ConnectionInput,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    c = db.get(EntraConnection, connection_id, with_for_update=True)
    if not c:
        raise HTTPException(404, "Connection not found")
    if c.tenant_id != str(data.tenant_id):
        raise HTTPException(422, "Create a separate connection for another tenant")
    if not data.name.strip():
        raise HTTPException(422, "Name the connection")
    cipher()
    c.name, c.client_id, c.enabled = data.name.strip(), str(data.client_id), data.enabled
    if data.client_secret:
        c.secret = cipher().encrypt(data.client_secret.encode()).decode()
    revoke(db, select(EntraIdentity.user_id).where(EntraIdentity.connection_id == c.id))
    db.execute(delete(EntraFlow).where(EntraFlow.connection_id == c.id))
    db.add(
        Audit(actor_id=user.id, action="sso_connection_updated", details={"connection_id": c.id})
    )
    db.commit()
    return connection_dict(c)


@router.post("/admin/sso/{connection_id}/identities", status_code=201)
def link_identity(
    connection_id: int,
    data: IdentityInput,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.get(EntraConnection, connection_id, with_for_update=True):
        raise HTTPException(404, "Connection not found")
    target = db.get(User, data.user_id)
    if not target or target.automation or not target.active:
        raise HTTPException(422, "Choose an active human user")
    db.add(
        EntraIdentity(connection_id=connection_id, object_id=str(data.object_id), user_id=target.id)
    )
    db.add(
        Audit(
            actor_id=user.id,
            action="sso_identity_linked",
            details={"connection_id": connection_id, "user_id": target.id},
        )
    )
    db.commit()
    return {"ok": True}


@router.delete("/admin/sso/{connection_id}/identities/{object_id}")
def unlink_identity(
    connection_id: int,
    object_id: UUID,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    db.get(EntraConnection, connection_id, with_for_update=True)
    identity = db.get(EntraIdentity, (connection_id, str(object_id)))
    if not identity:
        raise HTTPException(404, "Identity not found")
    revoke(db, [identity.user_id])
    db.add(
        Audit(
            actor_id=user.id,
            action="sso_identity_unlinked",
            details={"connection_id": connection_id, "user_id": identity.user_id},
        )
    )
    db.delete(identity)
    db.commit()
    return {"ok": True}


@router.get("/auth/providers")
def providers(db: Session = Depends(get_db)):
    if not os.getenv("SSO_ENCRYPTION_KEY"):
        return []
    return [
        {"id": c.id, "name": c.name}
        for c in db.scalars(
            select(EntraConnection)
            .where(EntraConnection.enabled.is_(True))
            .order_by(EntraConnection.name)
        )
    ]


@router.post("/auth/entra/start/{connection_id}")
def start(connection_id: int, request: Request, db: Session = Depends(get_db)):
    from .main import check_login_rate

    if (
        request.headers.get("origin") != origin()
        or request.headers.get("x-requested-with") != "RapidSupportHub"
    ):
        raise HTTPException(403, "Invalid request origin")
    check_login_rate(request)
    cipher()
    c = db.get(EntraConnection, connection_id)
    if not c or not c.enabled:
        raise HTTPException(404, "Sign-in provider unavailable")
    state, browser, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
    db.execute(delete(EntraFlow).where(EntraFlow.expires_at < now()))
    db.add(
        EntraFlow(
            digest=digest(state),
            connection_id=c.id,
            browser_digest=digest(browser),
            nonce=nonce,
            verifier=verifier,
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    params = {
        "client_id": c.client_id,
        "response_type": "code",
        "redirect_uri": origin() + CALLBACK,
        "response_mode": "query",
        "scope": "openid profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("="),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    from fastapi.responses import JSONResponse

    response = JSONResponse(
        {
            "url": f"https://login.microsoftonline.com/{c.tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"
        }
    )
    response.set_cookie(
        COOKIE, browser, httponly=True, secure=secure(), samesite="lax", max_age=600, path=CALLBACK
    )
    return response


@lru_cache(maxsize=64)
def signing_keys(tenant_id):
    return jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        lifespan=300,
        timeout=10,
    )


def validate_token(token, c, nonce):
    key = signing_keys(c.tenant_id).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=c.client_id,
        issuer=f"https://login.microsoftonline.com/{c.tenant_id}/v2.0",
        leeway=30,
        options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "nonce", "tid", "oid"]},
    )
    if claims["tid"] != c.tenant_id or not secrets.compare_digest(str(claims["nonce"]), nonce):
        raise ValueError("Invalid tenant or nonce")
    return str(UUID(claims["oid"]))


def exchange(c, code, verifier):
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.post(
            f"https://login.microsoftonline.com/{c.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": c.client_id,
                "client_secret": cipher().decrypt(c.secret.encode()).decode(),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": origin() + CALLBACK,
                "code_verifier": verifier,
            },
        )
        response.raise_for_status()
        return response.json()["id_token"]


@router.get("/auth/entra/callback")
def callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    response = RedirectResponse(origin() + "/?sso_error=failed", status_code=303)
    response.delete_cookie(COOKIE, path=CALLBACK, secure=secure(), samesite="lax")
    browser = request.cookies.get(COOKIE, "")
    if not state or not browser:
        return response
    # Atomic consumption prevents replay, including concurrent callbacks.
    flow = db.execute(
        delete(EntraFlow)
        .where(
            EntraFlow.digest == digest(state),
            EntraFlow.browser_digest == digest(browser),
            EntraFlow.expires_at > now(),
        )
        .returning(EntraFlow)
    ).scalar_one_or_none()
    db.commit()
    if not flow or error or not code:
        return response
    # Hold the connection lock through issuance so a disable/unlink cannot race sign-in.
    c = db.get(EntraConnection, flow.connection_id, with_for_update=True)
    if not c or not c.enabled:
        return response
    try:
        object_id = validate_token(exchange(c, code, flow.verifier), c, flow.nonce)
    except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, InvalidToken, HTTPException):
        return response
    linked = db.get(EntraIdentity, (c.id, object_id))
    user = db.get(User, linked.user_id) if linked else None
    if not user or not user.active or user.automation:
        response.headers["location"] = origin() + "/?sso_error=access"
        return response
    from .auditing import actor

    actor(user)
    raw, credential = issue(db, user, kind="sso", name="Microsoft Entra")
    actor(user, credential)
    db.add(Audit(actor_id=user.id, action="sso_signed_in", details={"connection_id": c.id}))
    db.commit()
    response.headers["location"] = origin() + "/"
    response.set_cookie(
        "rsh_session",
        raw,
        httponly=True,
        secure=secure(),
        samesite="strict",
        max_age=43200,
        path="/api",
    )
    return response
