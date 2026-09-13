import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

test_url = os.getenv("RSH_TEST_DATABASE_URL")
if test_url and not test_url.endswith("/rsh_test"):
    raise RuntimeError("External integration tests must target the dedicated rsh_test database")
os.environ["DATABASE_URL"] = test_url or "sqlite:///" + str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["ADMIN_PASSWORD"] = "Test-only-initial-123!"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()

import pytest
from app.db import Base, SessionLocal, engine, now
from app.main import app, attempts
from app.models import Audit, Cycle, Ticket, User
from app.security import issue
from app.sla import calendar_minutes, elapsed
from fastapi.testclient import TestClient
from sqlalchemy import select

HEADERS = {"origin": "http://localhost:5173", "x-requested-with": "RapidSupportHub"}


@pytest.fixture
def setup():
    Base.metadata.drop_all(engine)
    attempts.clear()
    with TestClient(app, headers=HEADERS) as client:
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "username": "SupportAdmin",
                    "password": os.environ["ADMIN_PASSWORD"],
                },
            ).status_code
            == 200
        )
        assert client.get("/api/tickets").status_code == 403
        assert (
            client.post(
                "/api/auth/password",
                json={
                    "current_password": os.environ["ADMIN_PASSWORD"],
                    "new_password": "Changed-test-password-456!",
                },
            ).status_code
            == 200
        )
        company = client.post("/api/admin/companies", json={"name": "Acme"}).json()["id"]
        other_company = client.post("/api/admin/companies", json={"name": "Other"}).json()["id"]
        product = client.post("/api/admin/products", json={"name": "RapidCube"}).json()["id"]
        users = {}
        for name, roles, org, automation in [
            ("alice", ["customer_own"], company, False),
            ("bob", ["customer_own", "customer_company"], company, False),
            ("eve", ["customer_company"], other_company, False),
            ("dev", ["developer"], None, False),
            ("bot", ["agent"], None, True),
        ]:
            result = client.post(
                "/api/admin/users",
                json={
                    "username": name,
                    "name": name.title(),
                    "password": "Temporary-test-123!",
                    "roles": roles,
                    "company_id": org,
                    "automation": automation,
                },
            )
            assert result.status_code == 201, result.text
            user = result.json()
            with SessionLocal() as db:
                record = db.get(User, user["id"])
                record.must_change_password = False
                raw, _ = issue(db, record)
                db.commit()
            users[name] = {"Authorization": "Bearer " + raw}
            users[name + "_id"] = user["id"]
        yield client, company, other_company, product, users


def ticket(client, company, product, **kwargs):
    headers = kwargs.pop("headers", None)
    result = client.post(
        "/api/tickets",
        json={
            "title": "Export is failing",
            "description": "An unexpected error",
            "company_id": company,
            "product_id": product,
            **kwargs,
        },
        headers=headers,
    )
    assert result.status_code == 201, result.text
    return result.json()


def policy(client, company):
    result = client.put(
        "/api/admin/policies",
        json={
            "company_id": company,
            "name": "Critical",
            "config": {
                "targets": [
                    {
                        "severity": "sev3",
                        "first_response": 30,
                        "resolution": 240,
                        "reply": 45,
                        "update": 60,
                    }
                ]
            },
        },
    )
    assert result.status_code == 200, result.text


def test_company_and_private_visibility(setup):
    client, company, other, product, users = setup
    alice = ticket(client, company, product, headers=users["alice"])
    bob = ticket(client, company, product, headers=users["bob"])
    eve = ticket(client, other, product, headers=users["eve"])
    bug = ticket(client, None, product, kind="bug", reproduction="Secret internal details")
    client.patch(
        f"/api/tickets/{alice['id']}",
        json={"version": alice["version"], "linked_bug_id": bug["id"]},
    )
    client.post(
        f"/api/tickets/{alice['id']}/messages",
        json={"body": "Internal investigation", "internal": True},
    )
    own = client.get("/api/tickets", headers=users["alice"]).json()
    assert [t["id"] for t in own] == [alice["id"]]
    assert len(client.get("/api/tickets", headers=users["bob"]).json()) == 2
    for id in [eve["id"], bug["id"], bob["id"]]:
        assert client.get(f"/api/tickets/{id}", headers=users["alice"]).status_code == 404
    detail = client.get(f"/api/tickets/{alice['id']}", headers=users["alice"]).json()
    assert detail["messages"] == []
    assert "linked_bug_id" not in detail and "audit" not in detail
    assert (
        client.post(
            f"/api/tickets/{alice['id']}/messages",
            json={"body": "hidden", "internal": True},
            headers=users["alice"],
        ).status_code
        == 403
    )
    spoof = ticket(client, other, product, headers=users["alice"])
    assert spoof["company_id"] == company


def test_first_human_response_and_reply_clock(setup):
    client, company, _, product, users = setup
    policy(client, company)
    t = ticket(client, company, product, headers=users["alice"])
    route = f"/api/tickets/{t['id']}/messages"
    bot = client.post(route, json={"body": "Automated acknowledgment"}, headers=users["bot"]).json()
    assert all(c["completed_at"] is None for c in bot["sla"])
    private = client.post(route, json={"body": "Investigating", "internal": True}).json()
    assert all(c["completed_at"] is None for c in private["sla"])
    reply = client.post(route, json={"body": "I am investigating your issue."}).json()
    first = next(c for c in reply["sla"] if c["metric"] == "first_response")
    assert first["completed_at"] and first["actor_id"] == 1
    client.post(route, json={"body": "Here are more details"}, headers=users["alice"])
    client.post(route, json={"body": "Another detail"}, headers=users["alice"])
    with SessionLocal() as db:
        pending = db.scalars(
            select(Cycle).where(Cycle.ticket_id == t["id"], Cycle.metric == "reply")
        ).all()
        assert len(pending) == 1
    reply = client.post(route, json={"body": "Thank you, received."}).json()
    assert next(c for c in reply["sla"] if c["metric"] == "reply")["completed_at"]


def test_resolution_approval_rejection_and_concurrency(setup):
    client, company, _, product, users = setup
    policy(client, company)
    t = ticket(client, company, product, headers=users["alice"])
    url = f"/api/tickets/{t['id']}"
    assert (
        client.patch(url, json={"version": t["version"], "status": "pending_approval"}).status_code
        == 422
    )
    resolved = client.patch(
        url,
        json={
            "version": t["version"],
            "status": "pending_approval",
            "resolution": "Fixed the export endpoint",
        },
    ).json()
    assert resolved["status"] == "pending_approval"
    assert next(c for c in resolved["sla"] if c["metric"] == "resolution")["completed_at"]
    assert (
        client.patch(url, json={"version": t["version"], "status": "in_progress"}).status_code
        == 409
    )
    assert (
        client.patch(
            url,
            json={"version": resolved["version"], "status": "in_progress"},
            headers=users["alice"],
        ).status_code
        == 422
    )
    reopened = client.patch(
        url,
        json={
            "version": resolved["version"],
            "status": "in_progress",
            "reason": "Still fails on CSV",
        },
        headers=users["alice"],
    ).json()
    assert reopened["status"] == "in_progress"
    detail = client.get(url).json()
    assert next(c for c in detail["sla"] if c["metric"] == "resolution")["completed_at"] is None
    resolved = client.patch(
        url,
        json={
            "version": detail["version"],
            "status": "pending_approval",
            "resolution": "Fixed CSV too",
        },
    ).json()
    closed = client.patch(
        url,
        json={"version": resolved["version"], "status": "closed"},
        headers=users["alice"],
    ).json()
    assert closed["status"] == "closed"
    assert client.post(url + "/messages", json={"body": "late"}).status_code == 422


def test_reports_and_api_keys_obey_permissions(setup):
    client, company, other, product, users = setup
    ticket(client, company, product, headers=users["alice"])
    ticket(client, other, product, headers=users["eve"])
    ticket(client, None, product, kind="bug")
    report = client.post(
        "/api/reports",
        json={
            "name": "All records",
            "shared": True,
            "config": {"group_by": "company", "metric": "count"},
        },
    ).json()
    alice = client.get(f"/api/reports/{report['id']}/run", headers=users["alice"]).json()
    assert alice["total_tickets"] == 1
    assert alice["rows"][0]["group"] == "Acme"
    assert client.post("/api/reports/run", json={}, headers=users["alice"]).status_code == 403
    assert (
        client.post(
            "/api/reports",
            json={"name": "Forbidden", "config": {}},
            headers=users["alice"],
        ).status_code
        == 403
    )
    key = client.post(
        "/api/admin/keys",
        json={"user_id": users["bot_id"], "name": "Read only", "scopes": ["read"]},
    ).json()
    auth = {"Authorization": "Bearer " + key["token"]}
    assert client.get("/api/tickets", headers=auth).status_code == 200
    assert client.get("/api/admin/users", headers=auth).status_code == 403
    assert (
        client.post(
            "/api/tickets",
            json={
                "title": "Automation write",
                "description": "No",
                "company_id": company,
                "product_id": product,
            },
            headers=auth,
        ).status_code
        == 403
    )
    assert client.get("/api/reports", headers=auth).status_code == 403
    assert client.delete(f"/api/admin/keys/{key['id']}").status_code == 200
    assert client.get("/api/tickets", headers=auth).status_code == 401


def test_attachments_and_csrf(setup):
    client, company, _, product, users = setup
    t = ticket(client, company, product, headers=users["alice"])
    a = client.post(
        f"/api/tickets/{t['id']}/attachments?internal=true",
        files={"file": ("../../secret.txt", b"private")},
    ).json()
    assert a["filename"] == "secret.txt"
    assert client.get(f"/api/attachments/{a['id']}", headers=users["alice"]).status_code == 404
    assert client.get(f"/api/attachments/{a['id']}").content == b"private"
    assert (
        client.post(
            "/api/admin/products",
            json={"name": "CSRF"},
            headers={"origin": "https://evil.example"},
        ).status_code
        == 403
    )


def test_business_calendar_dst_holidays_and_pauses(setup):
    client, company, _, product, users = setup
    config = {
        "coverage": "business",
        "timezone": "America/New_York",
        "weekdays": [0, 1, 2, 3, 4],
        "start": "09:00",
        "end": "17:00",
        "holidays": [],
    }
    # Friday before the March DST switch through Monday after it: two business days.
    assert calendar_minutes(datetime(2026, 3, 6, 14), datetime(2026, 3, 9, 21), config) == 960
    config["holidays"] = ["2026-03-09"]
    assert calendar_minutes(datetime(2026, 3, 6, 14), datetime(2026, 3, 9, 21), config) == 480
    t = ticket(client, company, product, headers=users["alice"])
    with SessionLocal() as db:
        record = db.get(Ticket, t["id"])
        record.sla_config = {"coverage": "24x7", "pause_waiting": True}
        start = datetime(2026, 1, 1, 12)
        cycle = db.scalar(
            select(Cycle).where(Cycle.ticket_id == t["id"], Cycle.metric == "resolution")
        )
        cycle.started_at = start
        db.add_all(
            [
                Audit(
                    ticket_id=t["id"],
                    actor_id=1,
                    action="status_changed",
                    details={"from": "new", "to": "waiting_customer"},
                    created_at=start + timedelta(minutes=10),
                ),
                Audit(
                    ticket_id=t["id"],
                    actor_id=1,
                    action="status_changed",
                    details={"from": "waiting_customer", "to": "in_progress"},
                    created_at=start + timedelta(minutes=50),
                ),
            ]
        )
        db.flush()
        assert elapsed(db, record, cycle, start + timedelta(minutes=60)) == 20


def test_policy_validation_and_snapshot(setup):
    client, company, _, product, users = setup
    assert (
        client.put(
            "/api/admin/policies",
            json={
                "company_id": company,
                "name": "Bad",
                "config": {
                    "timezone": "Made/Up",
                    "targets": [{"severity": "sev1", "first_response": 10, "resolution": 20}],
                },
            },
        ).status_code
        == 422
    )
    policy(client, company)
    t = ticket(client, company, product, headers=users["alice"])
    result = client.put(
        "/api/admin/policies",
        json={
            "company_id": company,
            "name": "New",
            "config": {"targets": [{"severity": "sev3", "first_response": 999, "resolution": 999}]},
        },
    )
    assert result.status_code == 200
    detail = client.get(f"/api/tickets/{t['id']}").json()
    assert next(c for c in detail["sla"] if c["metric"] == "first_response")["target_minutes"] == 30


def test_human_login_disabled_for_automation_and_role_validation(setup):
    client, company, _, product, users = setup
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "bot", "password": "Temporary-test-123!"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/admin/users",
            json={
                "username": "invalid",
                "name": "Invalid",
                "password": "Temporary-test-123!",
                "roles": ["customer_own"],
            },
        ).status_code
        == 422
    )
    assert (
        client.patch("/api/admin/users/1", json={"roles": ["agent"], "active": True}).status_code
        == 422
    )


def test_record_reports_and_csv_are_scoped_and_escaped(setup):
    client, company, other, product, users = setup
    t = ticket(client, company, product, title="=HYPERLINK(test)", headers=users["alice"])
    ticket(client, other, product, headers=users["eve"])
    report = client.post(
        "/api/reports",
        json={
            "name": "Records",
            "shared": True,
            "config": {
                "view": "records",
                "columns": ["id", "title", "company", "first_response_minutes"],
            },
        },
    ).json()
    result = client.get(f"/api/reports/{report['id']}/run", headers=users["alice"]).json()
    assert len(result["rows"]) == 1
    assert result["rows"][0]["id"] == t["id"]
    assert result["rows"][0]["first_response_minutes"] is None
    export = client.get(f"/api/reports/{report['id']}/run?export=true", headers=users["alice"])
    assert "'=HYPERLINK(test)" in export.text
    assert (
        client.post(
            "/api/reports/run", json={"view": "records", "columns": ["password_hash"]}
        ).status_code
        == 422
    )


def test_sla_statistics_preserve_breaches_and_human_attribution(setup):
    client, company, _, product, users = setup
    policy(client, company)
    t = ticket(client, company, product, headers=users["alice"])
    with SessionLocal() as db:
        first = db.scalar(
            select(Cycle).where(Cycle.ticket_id == t["id"], Cycle.metric == "first_response")
        )
        first.started_at = now() - timedelta(minutes=40)
        db.commit()
    client.post(
        f"/api/tickets/{t['id']}/messages",
        json={"body": "Investigating now"},
        headers=users["dev"],
    )
    report = client.post(
        "/api/reports/run",
        json={"metric": "first_response", "group_by": "first_response_agent"},
    ).json()
    row = report["rows"][0]
    assert row["group"] == "Dev"
    assert row["breached"] == 1 and row["compliance_percent"] == 0
    assert row["average_minutes"] >= 40 and row["median_minutes"] >= 40
    detail = client.get(f"/api/tickets/{t['id']}").json()
    resolved = client.patch(
        f"/api/tickets/{t['id']}",
        json={
            "version": detail["version"],
            "status": "pending_approval",
            "resolution": "Fixed",
        },
    ).json()
    # Resolving does not introduce an artificial zero-duration completed update.
    updates = [c for c in resolved["sla"] if c["metric"] == "update"]
    assert len(updates) == 2
