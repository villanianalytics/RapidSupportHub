"""Transactional record history plus correlated HTTP activity; never capture request bodies."""

import csv
import io
import json
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import DDL, event, func, inspect, or_, select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .db import SessionLocal, get_db
from .models import Audit, AuditEvent, User
from .security import require_admin

context = ContextVar("audit_context", default=None)
router = APIRouter(prefix="/api/admin/audit", tags=["Audit"])
SECRET = {
    "password_hash",
    "password_encrypted",
    "digest",
    "secret",
    "browser_digest",
    "nonce",
    "verifier",
    "storage_key",
}
CONTENT = {"body", "description", "reproduction", "resolution"}


def value(key, val):
    if val is None:
        return None
    if key in SECRET:
        return "[REDACTED]"
    if key in CONTENT:
        return {"characters": len(str(val)), "content": "[OMITTED]"}
    if isinstance(val, datetime):
        return val.isoformat()
    return val


def bind_request(request: Request):
    ctx = context.get()
    if ctx is not None:
        ctx["route"] = getattr(request.scope.get("route"), "path", "unmatched")[:200]


def sanitized_details(details):
    field = details.get("field", "") if isinstance(details, dict) else ""
    if isinstance(details, dict):
        return {
            k: value(field if k in {"from", "to"} and field else k, v)
            if not isinstance(v, (dict, list))
            else sanitized_details(v)
            for k, v in details.items()
        }
    if isinstance(details, list):
        return [sanitized_details(v) for v in details]
    return details


def actor(user, credential=None):
    ctx = context.get()
    if ctx is not None:
        ctx.update(
            actor_id=user.id,
            actor=user.username,
            auth_method=credential.kind if credential else "session",
            credential_id=credential.id if credential else None,
        )


def entry(action, resource="", resource_id="", details=None, **extra):
    ctx = context.get() or {}
    fields = {
        k: ctx[k]
        for k in (
            "request_id",
            "actor_id",
            "actor",
            "auth_method",
            "credential_id",
            "method",
            "route",
            "ip",
        )
        if k in ctx
    }
    if not ctx:
        fields.update(actor="System / maintenance", auth_method="system")
    fields.setdefault("request_id", str(uuid4()))
    return AuditEvent(
        **fields,
        action=action,
        resource=resource,
        resource_id=str(resource_id),
        details=details or {},
        **extra,
    )


@event.listens_for(Session, "before_flush")
def capture(db, flush_context, instances):
    pending = db.info.setdefault("audit_pending", [])
    for obj in list(db.new) + list(db.dirty) + list(db.deleted):
        if isinstance(obj, AuditEvent):
            if obj in db.dirty or obj in db.deleted:
                raise RuntimeError("Audit history is append-only")
            continue
        if isinstance(obj, Audit):
            if context.get() is not None and not context.get().get("actor_id"):
                user = db.get(User, obj.actor_id)
                if user:
                    actor(user)
            db.add(
                entry(
                    obj.action,
                    "tickets" if obj.ticket_id else "business_event",
                    obj.ticket_id or "",
                    sanitized_details(obj.details or {}),
                    outcome="success",
                )
            )
            continue
        state = inspect(obj)
        operation = "created" if obj in db.new else "deleted" if obj in db.deleted else "updated"
        changes = {}
        for attr in state.mapper.column_attrs:
            key = attr.key
            history = state.attrs[key].history
            if operation == "updated" and not history.has_changes():
                continue
            before = history.deleted[0] if history.deleted else None
            after = getattr(obj, key)
            changes[key] = {
                "before": value(key, after if operation == "deleted" else before),
                "after": None if operation == "deleted" else value(key, after),
            }
        if changes:
            pending.append((obj, operation, changes))


@event.listens_for(Session, "after_flush_postexec")
def persist(db, flush_context):
    for obj, operation, changes in db.info.pop("audit_pending", []):
        state = inspect(obj)
        key = ":".join(
            str(value(col.key, getattr(obj, col.key))) for col in state.mapper.primary_key
        )
        if operation == "created":
            changes = {
                attr.key: {"before": None, "after": value(attr.key, getattr(obj, attr.key))}
                for attr in state.mapper.column_attrs
            }
        db.add(
            entry(
                f"{state.mapper.local_table.name}.{operation}",
                state.mapper.local_table.name,
                key,
                {"changes": changes},
                outcome="success",
            )
        )


@event.listens_for(Session, "after_rollback")
def clear_pending(db):
    db.info.pop("audit_pending", None)


@event.listens_for(Session, "do_orm_execute", retval=True)
def bulk_changes(state):
    if not (state.is_delete or state.is_update):
        return state.invoke_statement()
    table = state.statement.table
    if table.name == "audit_events":
        raise RuntimeError("Audit history is append-only")
    # Bulk SQL bypasses normal ORM history (credential revocation, watchers, notifications).
    before = (
        state.session.execute(select(*table.c).where(*state.statement._where_criteria))
        .mappings()
        .all()
    )
    result = state.invoke_statement()
    for row in before:
        key = ":".join(str(value(c.name, row[c.name])) for c in table.primary_key)
        after = None
        if state.is_update:
            after = (
                state.session.execute(
                    select(*table.c).where(*[c == row[c.name] for c in table.primary_key])
                )
                .mappings()
                .first()
            )
        changes = {
            k: {"before": value(k, v), "after": value(k, after[k]) if after else None}
            for k, v in row.items()
            if after is None or v != after[k]
        }
        if changes:
            state.session.add(
                entry(
                    f"{table.name}.deleted" if state.is_delete else f"{table.name}.updated",
                    table.name,
                    key,
                    {"changes": changes},
                    outcome="success",
                )
            )
    return result


def save_event(record):
    with SessionLocal() as db:
        db.add(record)
        db.commit()


async def middleware(request, call_next):
    if not request.url.path.startswith("/api/") or request.url.path == "/api/health":
        return await call_next(request)
    ctx = {
        "request_id": str(uuid4()),
        "method": request.method,
        "ip": request.client.host[:100] if request.client else "",
        "route": "",
    }
    token = context.set(ctx)
    start = time.monotonic()
    try:
        # A durable start records interrupted requests too. No URL query or body is retained.
        await run_in_threadpool(save_event, entry("request.started", outcome="started"))
        try:
            response = await call_next(request)
        except Exception:
            await run_in_threadpool(
                save_event, entry("request.failed", outcome="failure", status=500)
            )
            raise
        route = request.scope.get("route")
        ctx["route"] = getattr(route, "path", "unmatched")[:200]
        name = ctx.get("activity", getattr(route, "name", "unmatched"))
        outcome = (
            "success"
            if response.status_code < 400
            else "denied"
            if response.status_code in (401, 403)
            else "failure"
        )
        if "sso_error=" in response.headers.get("location", ""):
            outcome = "failure"
        await run_in_threadpool(
            save_event,
            entry(
                f"request.{name}",
                resource=ctx["route"],
                resource_id=":".join(str(v) for v in request.path_params.values()),
                outcome=outcome,
                status=response.status_code,
                details={
                    "duration_ms": round((time.monotonic() - start) * 1000),
                    **(
                        {"attempted_username": ctx["attempted_username"]}
                        if "attempted_username" in ctx
                        else {}
                    ),
                },
            ),
        )
        response.headers["X-Request-ID"] = ctx["request_id"]
        return response
    finally:
        context.reset(token)


def timestamp(raw):
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        raise HTTPException(422, "Use an ISO date/time") from None


def serialize(row):
    return {c.name: getattr(row, c.name) for c in AuditEvent.__table__.columns}


@router.get("")
def history(
    q: str = Query("", max_length=160),
    action: str = "",
    resource: str = "",
    resource_id: str = "",
    actor_id: int | None = None,
    outcome: str = "",
    request_id: str = "",
    since: str = "",
    until: str = "",
    snapshot: int = Query(0, ge=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    export: bool = False,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if context.get() is not None:
        context.get()["activity"] = "audit_export" if export else "audit_view"
    snapshot = snapshot or db.scalar(select(func.max(AuditEvent.id))) or 0
    query = select(AuditEvent).where(AuditEvent.id <= snapshot)
    for field, val in (
        ("action", action),
        ("resource", resource),
        ("resource_id", resource_id),
        ("actor_id", actor_id),
        ("outcome", outcome),
        ("request_id", request_id),
    ):
        if val is not None and val != "":
            query = query.where(getattr(AuditEvent, field) == val)
    if q:
        query = query.where(
            or_(
                *[
                    getattr(AuditEvent, f).icontains(q, autoescape=True)
                    for f in ("actor", "action", "resource", "resource_id", "request_id", "ip")
                ]
            )
        )
    if since:
        query = query.where(AuditEvent.created_at >= timestamp(since))
    if until:
        query = query.where(AuditEvent.created_at <= timestamp(until))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    if export and total > 10000:
        raise HTTPException(422, "Narrow filters to 10,000 or fewer events before exporting")
    rows = db.scalars(
        query.order_by(AuditEvent.id.desc())
        .offset(0 if export else offset)
        .limit(10000 if export else limit)
    ).all()
    if export:
        out = io.StringIO()
        writer = csv.writer(out)
        fields = [c.name for c in AuditEvent.__table__.columns]
        writer.writerow(fields)
        for row in rows:
            values = serialize(row)
            cells = [
                json.dumps(values[f]) if isinstance(values[f], dict) else str(values[f] or "")
                for f in fields
            ]
            writer.writerow(
                ["'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for v in cells]
            )
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit-events.csv"'},
        )
    return {"total": total, "snapshot": snapshot, "items": [serialize(row) for row in rows]}


def initialize(db):
    """One-time import of existing business audit records, without fabricating request metadata."""
    connection = db.connection()
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION rsh_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit history is append-only'; END; $$"
            )
        )
        for name, clause in (
            ("audit_immutable", "UPDATE OR DELETE ON audit_events FOR EACH ROW"),
            ("audit_no_truncate", "TRUNCATE ON audit_events FOR EACH STATEMENT"),
        ):
            if not connection.scalar(
                text(
                    "SELECT 1 FROM pg_trigger WHERE tgrelid='audit_events'::regclass AND tgname=:name"
                ),
                {"name": name},
            ):
                connection.execute(
                    text(
                        f"CREATE TRIGGER {name} BEFORE {clause} EXECUTE FUNCTION rsh_audit_immutable()"
                    )
                )
    elif connection.dialect.name == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS audit_no_{operation.lower()} BEFORE {operation} ON audit_events BEGIN SELECT RAISE(ABORT, 'Audit history is append-only'); END"
                )
            )
    db.commit()
    if db.scalar(select(AuditEvent.id).where(AuditEvent.action == "audit.enabled").limit(1)):
        return
    for old in db.scalars(select(Audit).order_by(Audit.id)):
        user = db.get(User, old.actor_id)
        db.add(
            AuditEvent(
                request_id=str(uuid4()),
                created_at=old.created_at,
                actor_id=old.actor_id,
                actor=user.username if user else "Unknown",
                auth_method="legacy",
                action=old.action,
                resource="legacy_audit",
                resource_id=str(old.id),
                outcome="success",
                details={
                    "ticket_id": old.ticket_id,
                    "legacy": sanitized_details(old.details),
                    "note": "Imported historical event; original request metadata unavailable",
                },
            )
        )
    db.add(entry("audit.enabled", outcome="success"))
    db.commit()


# Enforce append-only records even for accidental direct SQL writes.

for operation in ("UPDATE", "DELETE"):
    event.listen(
        AuditEvent.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER audit_no_{operation.lower()} BEFORE {operation} ON audit_events "
            "BEGIN SELECT RAISE(ABORT, 'Audit history is append-only'); END"
        ).execute_if(dialect="sqlite"),
    )
event.listen(
    AuditEvent.__table__,
    "after_create",
    DDL(
        "CREATE OR REPLACE FUNCTION rsh_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION 'Audit history is append-only'; END; $$"
    ).execute_if(dialect="postgresql"),
)
event.listen(
    AuditEvent.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION rsh_audit_immutable()"
    ).execute_if(dialect="postgresql"),
)
