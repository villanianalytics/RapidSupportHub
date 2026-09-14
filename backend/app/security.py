import hashlib
import os
import secrets
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, now
from .models import Credential, Ticket, User

passwords = PasswordHash.recommended()
STAFF_ROLES = {"admin", "agent", "developer"}
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AutomationKey",
    description="Scoped automation API key. Interactive portal clients use the session cookie.",
)


def staff(user):
    return bool(STAFF_ROLES.intersection(user.roles))


def admin(user):
    return "admin" in user.roles


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue(db, user, kind="session", name="Session", scopes=None, days=None):
    raw = ("rsh_" if kind == "api" else "") + secrets.token_urlsafe(40)
    credential = Credential(
        user_id=user.id,
        digest=digest(raw),
        kind=kind,
        name=name,
        scopes=scopes or ["read", "write", "reports"],
        expires_at=now() + (timedelta(days=days) if days else timedelta(hours=12)),
    )
    db.add(credential)
    db.flush()
    return raw, credential


def identity(
    request: Request,
    db: Session = Depends(get_db),
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    header = request.headers.get("authorization", "")
    bearer = header[7:] if header.lower().startswith("bearer ") else None
    raw = bearer or request.cookies.get("rsh_session")
    credential = (
        db.scalar(select(Credential).where(Credential.digest == digest(raw))) if raw else None
    )
    if not credential or credential.expires_at < now():
        raise HTTPException(401, "Sign in to continue")
    user = db.get(User, credential.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account unavailable")
    from .auditing import actor

    actor(user, credential)
    if not bearer and request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        allowed = {
            os.getenv("APP_ORIGIN", "http://localhost:5173"),
            str(request.base_url).rstrip("/"),
        }
        if origin not in allowed or request.headers.get("x-requested-with") != "RapidSupportHub":
            raise HTTPException(403, "Invalid request origin")
    if (
        user.must_change_password
        and credential.kind != "sso"
        and request.url.path
        not in {
            "/api/auth/me",
            "/api/auth/password",
            "/api/auth/logout",
        }
    ):
        raise HTTPException(403, "Change your temporary password first")
    if credential.kind == "api":
        needed = "read" if request.method in {"GET", "HEAD"} else "write"
        if request.url.path.startswith("/api/reports"):
            needed = "reports"
        if needed not in credential.scopes:
            raise HTTPException(403, "API credential lacks the required scope")
        if (
            request.url.path.startswith(("/api/admin", "/api/auth"))
            and request.url.path != "/api/auth/me"
        ):
            raise HTTPException(403, "Use an interactive administrator session")
    request.state.credential = credential
    return user


def require_admin(user: User = Depends(identity)):
    if not admin(user):
        raise HTTPException(403, "Administrator access required")
    return user


def visible_query(user):
    query = select(Ticket)
    if staff(user):
        return query
    conditions = []
    if "customer_own" in user.roles:
        conditions.append(Ticket.creator_id == user.id)
    if "customer_company" in user.roles and user.company_id:
        conditions.append(Ticket.company_id == user.company_id)
    from sqlalchemy import false, or_

    return query.where(Ticket.kind == "support", or_(*conditions) if conditions else false())


def ticket_access(db, user, ticket_id):
    ticket = db.scalar(visible_query(user).where(Ticket.id == ticket_id).with_for_update())
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket
