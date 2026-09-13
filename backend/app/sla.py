from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .db import now
from .models import Audit, Cycle


def calendar_minutes(start, end, config):
    if end <= start:
        return 0.0
    if not config or config.get("coverage") == "24x7":
        return (end - start).total_seconds() / 60
    zone = ZoneInfo(config["timezone"])
    day = start.replace(tzinfo=timezone.utc).astimezone(zone).date()
    last = end.replace(tzinfo=timezone.utc).astimezone(zone).date()
    total = 0.0
    while day <= last:
        if day.weekday() in config["weekdays"] and day.isoformat() not in config["holidays"]:
            opening = (
                datetime.combine(day, time.fromisoformat(config["start"]), zone)
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
            closing = (
                datetime.combine(day, time.fromisoformat(config["end"]), zone)
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )
            total += max(0, (min(end, closing) - max(start, opening)).total_seconds() / 60)
        day += timedelta(days=1)
    return total


def elapsed(db, ticket, cycle, at=None):
    end = cycle.completed_at or at or now()
    config = ticket.sla_config or {}
    events = db.scalars(
        select(Audit)
        .where(Audit.ticket_id == ticket.id, Audit.action == "status_changed")
        .order_by(Audit.created_at, Audit.id)
    ).all()
    status, cursor, total = "new", cycle.started_at, 0.0

    def active(value):
        return value not in {"pending_approval", "closed"} and not (
            value == "waiting_customer" and config.get("pause_waiting", False)
        )

    for event in events:
        if event.created_at <= cycle.started_at:
            status = event.details["to"]
            continue
        if event.created_at > end:
            break
        if active(status):
            total += calendar_minutes(cursor, event.created_at, config)
        cursor, status = event.created_at, event.details["to"]
    if active(status):
        total += calendar_minutes(cursor, end, config)
    return max(0.0, total)


def target_for(ticket, metric):
    targets = (ticket.sla_config or {}).get("targets", [])
    matches = [
        x
        for x in targets
        if x["severity"] == ticket.severity and x["incident_type"] in {ticket.incident_type, "*"}
    ]
    matches.sort(key=lambda x: x["incident_type"] == "*")
    return matches[0].get(metric) if matches else None


def start_cycle(db, ticket, metric, at=None, always=False):
    target = target_for(ticket, metric)
    if target or always:
        db.add(
            Cycle(
                ticket_id=ticket.id,
                metric=metric,
                target_minutes=target,
                started_at=at or now(),
            )
        )


def cycles(db, ticket):
    return db.scalars(select(Cycle).where(Cycle.ticket_id == ticket.id).order_by(Cycle.id)).all()


def due_at(at, remaining, config):
    if not config or config.get("coverage") == "24x7":
        return at + timedelta(minutes=max(0, remaining))
    # Binary search in real time preserves local business windows and DST transitions.
    lo, hi = at, at + timedelta(days=1)
    while calendar_minutes(at, hi, config) < remaining and hi - at < timedelta(days=7300):
        hi = at + (hi - at) * 2
    if calendar_minutes(at, hi, config) < remaining:
        return None
    for _ in range(35):
        mid = lo + (hi - lo) / 2
        if calendar_minutes(at, mid, config) < remaining:
            lo = mid
        else:
            hi = mid
    return hi


def summary(db, ticket):
    result = []
    at = now()
    for cycle in cycles(db, ticket):
        used = elapsed(db, ticket, cycle, at)
        paused = not cycle.completed_at and (
            ticket.status in {"pending_approval", "closed"}
            or (
                ticket.status == "waiting_customer"
                and (ticket.sla_config or {}).get("pause_waiting")
            )
        )
        target = cycle.target_minutes
        state = (
            "cancelled"
            if cycle.cancelled
            else "breached"
            if target and used > target
            else "met"
            if cycle.completed_at and target
            else "measured"
            if cycle.completed_at
            else "paused"
            if paused
            else "at_risk"
            if target and used >= target * 0.8
            else "running"
        )
        deadline = (
            due_at(at, target - used, ticket.sla_config)
            if target and not cycle.completed_at and not paused and used <= target
            else None
        )
        result.append(
            {
                "id": cycle.id,
                "metric": cycle.metric,
                "target_minutes": target,
                "elapsed_minutes": round(used, 2),
                "state": state,
                "completed_at": cycle.completed_at,
                "actor_id": cycle.actor_id,
                "due_at": deadline,
                "paused": bool(paused),
            }
        )
    return result
