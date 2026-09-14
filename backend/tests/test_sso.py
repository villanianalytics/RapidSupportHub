# ruff: noqa: I001
# Initialize the isolated test database before importing application modules.
from test_api import HEADERS, setup  # noqa: F401

import json
import time
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from app import entra
from app.db import SessionLocal, now
from app.models import Audit, Credential, EntraConnection, EntraFlow, User
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
OBJECT = "33333333-3333-4333-8333-333333333333"
SECRET = "test-only-entra-client-secret"


@pytest.fixture
def sso(request, monkeypatch):
    client, company, other, product, users = request.getfixturevalue("setup")
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", Fernet.generate_key().decode())
    config = {
        "name": "Test organization",
        "tenant_id": TENANT,
        "client_id": CLIENT,
        "client_secret": SECRET,
        "enabled": True,
    }
    result = client.post("/api/admin/sso", json=config)
    assert result.status_code == 201, result.text
    connection_id = result.json()["id"]
    assert (
        client.post(
            f"/api/admin/sso/{connection_id}/identities",
            json={"object_id": OBJECT, "user_id": users["alice_id"]},
        ).status_code
        == 201
    )
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    keys = jwt.PyJWKClient("https://unused.invalid/keys")
    monkeypatch.setattr(keys, "fetch_data", lambda: {"keys": [jwk]})
    monkeypatch.setattr(entra, "signing_keys", lambda tenant: keys)
    return client, users, connection_id, private, config


def begin(client, connection_id):
    result = client.post(f"/api/auth/entra/start/{connection_id}")
    assert result.status_code == 200, result.text
    params = parse_qs(urlparse(result.json()["url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:5173/api/auth/entra/callback"]
    assert params["scope"] == ["openid profile"]
    return params


def token(private, params, **overrides):
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT,
        "tid": TENANT,
        "oid": OBJECT,
        "sub": "opaque-subject",
        "nonce": params["nonce"][0],
        "iat": int(time.time()),
        "nbf": int(time.time()) - 10,
        "exp": int(time.time()) + 300,
        **overrides,
    }
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-key"})


def finish(client, params):
    return client.get(
        "/api/auth/entra/callback",
        params={"state": params["state"][0], "code": "test-code"},
        follow_redirects=False,
    )


def test_sso_success_preserves_roles_and_local_password_requirement(sso, monkeypatch):
    client, users, cid, private, config = sso
    with SessionLocal() as db:
        db.get(User, users["alice_id"]).must_change_password = True
        db.commit()
    with TestClient(client.app, headers=HEADERS) as browser:
        params = begin(browser, cid)
        monkeypatch.setattr(entra, "exchange", lambda *args: token(private, params))
        result = finish(browser, params)
        assert result.status_code == 303 and result.headers["location"] == "http://localhost:5173/"
        me = browser.get("/api/auth/me").json()
        assert me["id"] == users["alice_id"] and me["roles"] == ["customer_own"]
        assert me["auth_method"] == "entra" and me["must_change_password"] is False
        assert browser.get("/api/tickets").status_code == 200
        assert browser.get("/api/admin/sso").status_code == 403
        assert (
            browser.post(
                "/api/auth/password",
                json={
                    "current_password": "Temporary-test-123!",
                    "new_password": "Another-temp-456!",
                },
            ).status_code
            == 422
        )
        assert "failed" in finish(browser, params).headers["location"]
        with SessionLocal() as db:
            assert db.get(User, users["alice_id"]).must_change_password
            assert len(db.scalars(select(Credential).where(Credential.kind == "sso")).all()) == 1
        assert client.delete(f"/api/admin/sso/{cid}/identities/{OBJECT}").status_code == 200
        assert browser.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "override",
    [
        {"aud": "wrong-client"},
        {"iss": "https://attacker.invalid"},
        {"tid": "wrong-tenant"},
        {"nonce": "wrong-nonce"},
        {"exp": 1},
        {"nbf": int(time.time()) + 3600},
        {"oid": "not-a-uuid"},
    ],
)
def test_sso_rejects_invalid_token_claims(sso, monkeypatch, override):
    client, users, cid, private, config = sso
    params = begin(client, cid)
    monkeypatch.setattr(entra, "exchange", lambda *args: token(private, params, **override))
    assert "failed" in finish(client, params).headers["location"]
    with SessionLocal() as db:
        assert not db.scalar(select(Credential).where(Credential.kind == "sso"))


def test_sso_rejects_forged_signature_and_unknown_identity(sso, monkeypatch):
    client, users, cid, private, config = sso
    params = begin(client, cid)
    fake = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(entra, "exchange", lambda *args: token(fake, params))
    assert "failed" in finish(client, params).headers["location"]
    params = begin(client, cid)
    monkeypatch.setattr(
        entra,
        "exchange",
        lambda *args: token(private, params, oid="44444444-4444-4444-8444-444444444444"),
    )
    assert "access" in finish(client, params).headers["location"]
    with SessionLocal() as db:
        assert not db.scalar(select(Credential).where(Credential.kind == "sso"))


def test_sso_state_cookie_expiry_disabled_and_denial(sso, monkeypatch):
    client, users, cid, private, config = sso
    params = begin(client, cid)
    with TestClient(client.app, headers=HEADERS) as other_browser:
        assert "failed" in finish(other_browser, params).headers["location"]
    with SessionLocal() as db:
        flow = db.scalar(select(EntraFlow))
        flow.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert "failed" in finish(client, params).headers["location"]
    params = begin(client, cid)
    denied = client.get(
        "/api/auth/entra/callback",
        params={
            "state": params["state"][0],
            "error": "access_denied",
            "error_description": "<script>untrusted</script>",
        },
        follow_redirects=False,
    )
    assert denied.headers["location"] == "http://localhost:5173/?sso_error=failed"
    params = begin(client, cid)
    assert (
        client.put(
            f"/api/admin/sso/{cid}", json={**config, "enabled": False, "client_secret": None}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/providers").json() == []
    assert "failed" in finish(client, params).headers["location"]
    assert client.post(f"/api/auth/entra/start/{cid}").status_code == 404


def test_sso_admin_permissions_and_secret_encryption(sso):
    client, users, cid, private, config = sso
    settings = client.get("/api/admin/sso")
    assert SECRET not in settings.text and settings.json()["server_ready"]
    assert client.get("/api/admin/sso", headers=users["dev"]).status_code == 403
    assert client.post("/api/admin/sso", json=config, headers=users["dev"]).status_code == 403
    assert (
        client.post(
            f"/api/admin/sso/{cid}/identities",
            json={"object_id": OBJECT, "user_id": users["bot_id"]},
        ).status_code
        == 422
    )
    assert (
        client.put(f"/api/admin/sso/{cid}", json={**config, "tenant_id": OBJECT}).status_code == 422
    )
    assert (
        client.post(
            f"/api/auth/entra/start/{cid}", headers={"origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    with SessionLocal() as db:
        c = db.get(EntraConnection, cid)
        assert c.secret != SECRET and entra.cipher().decrypt(c.secret.encode()).decode() == SECRET
        assert SECRET not in str([a.details for a in db.scalars(select(Audit))])
        from app.models import AuditEvent

        assert SECRET not in str([a.details for a in db.scalars(select(AuditEvent))])


def test_token_exchange_uses_pkce_and_fixed_tenant_endpoint(monkeypatch):
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", Fernet.generate_key().decode())
    c = SimpleNamespace(
        tenant_id=TENANT, client_id=CLIENT, secret=entra.cipher().encrypt(SECRET.encode()).decode()
    )
    original_client = httpx.Client

    def respond(request):
        assert str(request.url) == f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
        fields = parse_qs(request.content.decode())
        assert fields["code_verifier"] == ["test-verifier"] and fields["client_secret"] == [SECRET]
        assert fields["grant_type"] == ["authorization_code"]
        return httpx.Response(200, json={"id_token": "token"})

    monkeypatch.setattr(
        entra.httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    assert entra.exchange(c, "code", "test-verifier") == "token"
