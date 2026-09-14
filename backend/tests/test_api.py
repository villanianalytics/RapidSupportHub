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
os.environ["EMAIL_WORKER_ENABLED"] = "false"

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


def test_account_reset_and_revocation(setup):
    client, company, other, product, users = setup
    path = f"/api/admin/users/{users['alice_id']}"
    assert (
        client.post(
            path + "/reset-password",
            headers=users["dev"],
            json={"temporary_password": "Replacement-temp-456!"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/admin/users/1/reset-password",
            json={"temporary_password": "Replacement-temp-456!"},
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/admin/users/{users['bot_id']}/require-password-change").status_code
        == 422
    )
    assert (
        client.post(
            path + "/reset-password", json={"temporary_password": "Replacement-temp-456!"}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me", headers=users["alice"]).status_code == 401
    with TestClient(app, headers=HEADERS) as customer:
        assert (
            customer.post(
                "/api/auth/login", json={"username": "alice", "password": "Temporary-test-123!"}
            ).status_code
            == 401
        )
        result = customer.post(
            "/api/auth/login", json={"username": "alice", "password": "Replacement-temp-456!"}
        )
        assert result.json()["must_change_password"]
        assert customer.get("/api/tickets").status_code == 403
        assert (
            customer.post(
                "/api/auth/password",
                json={
                    "current_password": "Replacement-temp-456!",
                    "new_password": "Personal-replacement-789!",
                },
            ).status_code
            == 200
        )
        assert customer.get("/api/tickets").status_code == 200
        assert client.post(path + "/require-password-change").status_code == 200
        assert customer.get("/api/auth/me").status_code == 401
        assert customer.post(
            "/api/auth/login", json={"username": "alice", "password": "Personal-replacement-789!"}
        ).json()["must_change_password"]


def test_watchers_notification_visibility_and_read_state(setup):
    client, company, other, product, users = setup
    t = ticket(client, company, product, headers=users["alice"])
    path = f"/api/tickets/{t['id']}"
    assert client.put(path + f"/watchers/{users['dev_id']}").status_code == 200
    assert client.put(path + f"/watchers/{users['eve_id']}").status_code == 422
    assert (
        client.put(path + f"/watchers/{users['bob_id']}", headers=users["alice"]).status_code == 403
    )
    assert client.get("/api/notifications", headers=users["dev"]).json()["unread_count"] == 1
    assert (
        client.post(
            path + "/messages", json={"body": "Private investigation", "internal": True}
        ).status_code
        == 201
    )
    assert client.get("/api/notifications", headers=users["alice"]).json()["items"] == []
    assert client.post(path + "/messages", json={"body": "We are investigating"}).status_code == 201
    inbox = client.get("/api/notifications", headers=users["alice"]).json()
    assert inbox["unread_count"] == 1
    n = inbox["items"][0]
    assert n["kind"] == "staff_reply"
    assert client.patch(f"/api/notifications/{n['id']}", headers=users["eve"]).status_code == 404
    assert client.patch(f"/api/notifications/{n['id']}", headers=users["alice"]).status_code == 200
    assert (
        client.get("/api/notifications?unread=true", headers=users["alice"]).json()["items"] == []
    )
    with SessionLocal() as db:
        dev = db.get(User, users["dev_id"])
        dev.roles = ["customer_own"]
        db.commit()
    assert client.get("/api/notifications", headers=users["dev"]).json()["items"] == []
    assert client.get(path, headers=users["dev"]).status_code == 404


def test_attention_queue_deadlines_and_unanswered(setup):
    client, company, other, product, users = setup
    policy(client, company)
    t = ticket(client, company, product, headers=users["alice"])
    with SessionLocal() as db:
        first = db.scalar(
            select(Cycle).where(Cycle.ticket_id == t["id"], Cycle.metric == "first_response")
        )
        first.started_at = now() - timedelta(minutes=26)
        db.commit()
    queue = client.get("/api/attention").json()
    assert {"at_risk", "unanswered", "unassigned"} <= set(queue["items"][0]["attention"])
    with SessionLocal() as db:
        first = db.scalar(
            select(Cycle).where(Cycle.ticket_id == t["id"], Cycle.metric == "first_response")
        )
        first.started_at = now() - timedelta(minutes=40)
        db.commit()
    assert client.get("/api/attention?reason=breached").json()["total"] == 1
    assert client.get("/api/attention", headers=users["alice"]).status_code == 403
    path = f"/api/tickets/{t['id']}"
    client.post(path + "/messages", json={"body": "Human response"})
    assert client.get("/api/attention?reason=unanswered").json()["total"] == 0
    client.post(path + "/messages", json={"body": "More help please"}, headers=users["alice"])
    assert client.get("/api/attention?reason=unanswered").json()["total"] == 1
    current = client.get(path).json()
    assert (
        client.patch(
            path,
            json={
                "version": current["version"],
                "status": "pending_approval",
                "resolution": "Fixed the export",
            },
        ).status_code
        == 200
    )
    assert client.get("/api/attention").json()["total"] == 0


def test_organization_views_and_atomic_bulk(setup):
    client, company, other, product, users = setup
    a = ticket(client, company, product, headers=users["alice"])
    b = ticket(client, company, product)
    bug = ticket(client, None, product, kind="bug")
    path = f"/api/tickets/{a['id']}/organization"
    changed = client.patch(
        path,
        json={
            "version": a["version"],
            "tags": [" Export ", "export", "urgent"],
            "duplicate_of_id": b["id"],
        },
    )
    assert changed.status_code == 200, changed.text
    a = changed.json()
    assert a["tags"] == ["export", "urgent"]
    assert [t["id"] for t in client.get("/api/tickets?tag=export").json()] == [a["id"]]
    assert "tags" not in client.get(f"/api/tickets/{a['id']}", headers=users["alice"]).json()
    assert client.get("/api/tickets?tag=export", headers=users["alice"]).status_code == 403
    assert (
        client.patch(
            f"/api/tickets/{b['id']}/organization",
            json={"version": b["version"], "duplicate_of_id": a["id"]},
        ).status_code
        == 422
    )
    assert (
        client.patch(path, json={"version": a["version"], "duplicate_of_id": bug["id"]}).status_code
        == 422
    )
    assert client.patch(path, json={"version": a["version"] - 1, "tags": []}).status_code == 409
    refs = [{"id": t["id"], "version": t["version"]} for t in [a, bug]]
    # The support mutation succeeds first; the later bug rejects customer approval.
    result = client.post(
        "/api/tickets/bulk",
        json={"tickets": refs, "status": "pending_approval", "resolution": "Fixed"},
    )
    assert result.status_code == 422
    current = client.get(f"/api/tickets/{a['id']}").json()
    assert current["status"] == "new" and current["version"] == a["version"]
    assert client.get("/api/notifications", headers=users["alice"]).json()["items"] == []
    result = client.post(
        "/api/tickets/bulk",
        json={"tickets": refs, "status": "in_progress", "assignee_id": users["dev_id"]},
    )
    assert result.status_code == 200, result.text
    assert all(
        t["assignee_id"] == users["dev_id"] and t["status"] == "in_progress" for t in result.json()
    )
    assert (
        client.post("/api/tickets/bulk", json={"tickets": refs, "status": "started"}).status_code
        == 409
    )
    assert (
        client.post(
            "/api/tickets/bulk", headers=users["alice"], json={"tickets": refs, "status": "started"}
        ).status_code
        == 403
    )
    view = client.post(
        "/api/views", json={"name": "Export issues", "config": {"tag": "export", "layout": "board"}}
    ).json()
    assert client.get("/api/views", headers=users["dev"]).json() == []
    assert client.delete(f"/api/views/{view['id']}", headers=users["dev"]).status_code == 404
    assert (
        client.post(
            "/api/views",
            headers=users["alice"],
            json={"name": "Private", "config": {"kind": "bug"}},
        ).status_code
        == 403
    )
    assert client.delete(f"/api/views/{view['id']}").status_code == 200


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


def test_comprehensive_audit(setup):
    import json

    from app.models import AuditEvent, Product
    from sqlalchemy import text, update
    from sqlalchemy.exc import DBAPIError

    client, company, _, product, users = setup
    item = ticket(client, company, product)
    changed = client.patch(
        f"/api/tickets/{item['id']}", json={"version": item["version"], "severity": "sev1"}
    )
    assert changed.status_code == 200
    request_id = changed.headers["x-request-id"]
    records = client.get("/api/admin/audit", params={"request_id": request_id}).json()["items"]
    assert {r["outcome"] for r in records} >= {"success", "started"}
    change = next(r for r in records if r["action"] == "tickets.updated")
    assert change["details"]["changes"]["severity"] == {"before": "sev3", "after": "sev1"}
    assert change["actor"] == "SupportAdmin" and change["route"] == "/api/tickets/{ticket_id}"
    assert any(r["status"] == 200 for r in records)
    stale = client.patch(
        f"/api/tickets/{item['id']}", json={"version": item["version"], "severity": "sev2"}
    )
    assert stale.status_code == 409
    rows = client.get(
        "/api/admin/audit", params={"request_id": stale.headers["x-request-id"]}
    ).json()["items"]
    assert any(r["outcome"] == "failure" for r in rows)
    assert not any(r["action"] == "tickets.updated" for r in rows)
    for who in ("alice", "dev", "bot"):
        assert client.get("/api/admin/audit", headers=users[who]).status_code == 403
        assert client.get("/api/admin/audit?export=true", headers=users[who]).status_code == 403
    key = client.post(
        "/api/admin/keys",
        json={
            "user_id": users["bot_id"],
            "name": "Audit test",
            "scopes": ["read"],
            "expires_days": 1,
        },
    ).json()
    read = client.get("/api/tickets", headers={"Authorization": "Bearer " + key["token"]})
    assert read.status_code == 200
    activity = client.get(
        "/api/admin/audit", params={"request_id": read.headers["x-request-id"]}
    ).json()["items"]
    automated = next(row for row in activity if row["outcome"] == "success")
    assert automated["auth_method"] == "api" and automated["credential_id"] == key["id"]
    assert automated["actor_id"] == users["bot_id"]
    assert key["token"] not in client.get("/api/admin/audit?export=true").text
    assert client.delete(f"/api/admin/keys/{key['id']}").status_code == 200
    assert client.get("/api/admin/audit?action=credentials.deleted").json()["total"] > 0
    result = client.get("/api/admin/audit?outcome=denied").json()
    assert result["total"] >= 6
    failure = client.post(
        "/api/auth/login", json={"username": "nonexistent", "password": "Never-log-this-secret!"}
    )
    assert failure.status_code == 401
    exported = client.get("/api/admin/audit?export=true")
    assert exported.status_code == 200
    assert "Never-log-this-secret" not in exported.text
    assert "Test-only-initial" not in exported.text
    assert "argon2" not in exported.text
    assert "[REDACTED]" in exported.text
    assert "nonexistent" in exported.text
    with SessionLocal() as db:
        record = db.get(Product, product)
        record.name = "Rolled back audit test"
        db.flush()
        db.rollback()
    assert client.get("/api/admin/audit?action=products.updated").json()["total"] == 0
    with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="append-only"):
            db.execute(update(AuditEvent).values(actor="tampered"))
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(text("DELETE FROM audit_events"))
        db.rollback()
    assert client.get("/api/admin/audit?since=invalid").status_code == 422
    assert client.get("/api/admin/audit?limit=101").status_code == 422
    frozen = client.get("/api/admin/audit?limit=1").json()
    stable = client.get(
        "/api/admin/audit", params={"snapshot": frozen["snapshot"], "limit": 1}
    ).json()
    assert stable["total"] == frozen["total"] and stable["items"] == frozen["items"]
    assert json.loads(json.dumps(records))


def test_amazon_ses_smtp_configuration(setup, monkeypatch):
    from app import mail
    from app.models import AuditEvent, SMTPConfiguration
    from cryptography.fernet import Fernet

    client, _, _, _, users = setup
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for who in ("alice", "dev", "bot"):
        assert client.get("/api/admin/email", headers=users[who]).status_code == 403
        assert client.put("/api/admin/email", json={}, headers=users[who]).status_code == 403
        assert client.post("/api/admin/email/test", headers=users[who]).status_code == 403

    payload = {
        "region": "us-east-1",
        "port": 587,
        "username": "AKIA-SES-SMTP-TEST",
        "password": "smtp-secret-that-must-never-leak",
        "from_email": "support@example.com",
        "from_name": "RapidSupportHub",
        "reply_to": "replies@example.com",
        "enabled": True,
    }
    assert client.put("/api/admin/email", json={**payload, "port": 25}).status_code == 422
    saved = client.put("/api/admin/email", json=payload)
    assert saved.status_code == 200
    assert "password" not in saved.json()
    assert saved.json()["endpoint"] == "email-smtp.us-east-1.amazonaws.com"
    assert mail.endpoint("cn-north-1") == "email-smtp.cn-north-1.amazonaws.com.cn"
    with SessionLocal() as db:
        record = db.get(SMTPConfiguration, 1)
        assert record.password_encrypted != payload["password"]
        events = list(db.scalars(select(AuditEvent)))
        assert payload["password"] not in str([event.details for event in events])
        changes = next(event for event in events if event.action == "smtp_configuration.created")
        assert changes.details["changes"]["password_encrypted"]["after"] == "[REDACTED]"

    checked = []
    monkeypatch.setattr(mail, "verify_connection", lambda record: checked.append(record.region))
    tested = client.post("/api/admin/email/test")
    assert tested.status_code == 200 and checked == ["us-east-1"]
    config = client.get("/api/admin/email").json()["configuration"]
    assert config["last_test_ok"] is True and config["has_password"] is True

    updated = client.put("/api/admin/email", json={**payload, "password": None, "enabled": False})
    assert updated.status_code == 200 and updated.json()["last_test_ok"] is None
    monkeypatch.setattr(mail, "verify_connection", lambda record: (_ for _ in ()).throw(OSError()))
    assert client.post("/api/admin/email/test").status_code == 422
    assert client.get("/api/admin/email").json()["configuration"]["last_test_ok"] is False


def test_notification_email_queue_delivery_and_permission_recheck(setup, monkeypatch):
    from app import mail
    from app.entra import cipher
    from app.models import EmailDelivery, SMTPConfiguration
    from cryptography.fernet import Fernet

    client, company, _, product, users = setup
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with SessionLocal() as db:
        db.get(User, users["alice_id"]).email = "alice@example.com"
        db.get(User, users["dev_id"]).email = "dev@example.com"
        db.add(
            SMTPConfiguration(
                id=1,
                region="us-east-1",
                port=587,
                username="smtp-user",
                password_encrypted=cipher().encrypt(b"smtp-password").decode(),
                from_email="support@example.com",
                from_name="RapidSupportHub",
                enabled=True,
            )
        )
        db.commit()

    created = ticket(client, company, product, headers=users["alice"])
    with SessionLocal() as db:
        queued = list(
            db.scalars(
                select(EmailDelivery).where(EmailDelivery.ticket_id == created["id"])
            )
        )
        assert {item.user_id for item in queued} == {users["alice_id"]}
        assert all(item.kind == "ticket_created" for item in queued)

    sent = []
    monkeypatch.setattr(mail, "_send", lambda config, message: sent.append(message))
    assert mail.deliver_pending() == 1
    assert {message["To"] for message in sent} == {"alice@example.com"}
    status = client.get("/api/admin/email/deliveries").json()
    assert status["counts"]["sent"] == 1

    assert (
        client.patch(
            f"/api/tickets/{created['id']}",
            headers=users["dev"],
            json={"version": created["version"], "severity": "sev2"},
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        alice = db.get(User, users["alice_id"])
        alice.active = False
        db.commit()
    sent.clear()
    assert mail.deliver_pending() == 1
    assert sent == []
    assert client.get("/api/admin/email/deliveries").json()["counts"]["suppressed"] == 1


def test_profiles_categories_and_assignment_rules(setup):
    from app.models import IssueCategory, SupportGroup

    client, company, _, product, users = setup
    issue_types = {
        item["name"]
        for item in client.get("/api/catalog").json()["categories"]
        if item["kind"] in {"bug", "both"}
    }
    assert {"Bug", "Question", "Enhancement"} <= issue_types
    dev = next(item for item in client.get("/api/admin/users").json() if item["id"] == users["dev_id"])
    updated = client.patch(
        f"/api/admin/users/{users['dev_id']}",
        json={
            "name": "Daniel Developer",
            "email": "daniel@example.com",
            "phone": "+1 555 010 0200",
            "roles": ["developer", "assigner"],
            "company_id": None,
            "manage_reports": dev["manage_reports"],
            "active": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+1 555 010 0200"
    with SessionLocal() as db:
        raw, _ = issue(db, db.get(User, users["dev_id"]))
        db.commit()
        users["dev"] = {"Authorization": "Bearer " + raw}

    category_result = client.post(
        "/api/admin/routing/categories",
        json={
            "name": "Data import enhancement",
            "kind": "both",
            "incident_type": "enhancement",
            "active": True,
        },
    )
    category = next(
        item for item in category_result.json()["categories"] if item["name"] == "Data import enhancement"
    )
    with SessionLocal() as db:
        assert db.get(IssueCategory, category["id"])

    group_result = client.post(
        "/api/admin/routing/groups", json={"name": "Data team", "description": ""}
    )
    group = next(item for item in group_result.json()["groups"] if item["name"] == "Data team")
    assert (
        client.put(
            f"/api/admin/routing/groups/{group['id']}/members",
            json={"user_ids": [users["dev_id"]]},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/admin/routing/rules",
            json={
                "category_id": category["id"],
                "strategy": "round_robin",
                "group_id": group["id"],
                "assignee_id": None,
            },
        ).status_code
        == 200
    )
    created = ticket(
        client,
        company,
        product,
        category_id=category["id"],
        incident_type="question",
    )
    assert created["category"] == "Data import enhancement"
    assert created["incident_type"] == "enhancement"
    assert created["assignee_id"] == users["dev_id"]
    assert created["submitter"]["email"] == ""

    assigner_update = client.patch(
        f"/api/tickets/{created['id']}",
        headers=users["dev"],
        json={"version": created["version"], "assignee_id": None},
    )
    assert assigner_update.status_code == 200
    agent_attempt = client.patch(
        f"/api/tickets/{created['id']}",
        headers=users["bot"],
        json={"version": assigner_update.json()["version"], "assignee_id": users["dev_id"]},
    )
    assert agent_attempt.status_code == 403
    with SessionLocal() as db:
        assert db.get(SupportGroup, group["id"])
