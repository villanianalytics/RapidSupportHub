"""Account administration, inbox, subscriptions, saved views and bulk actions."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import schemas as s
from . import workspace
from .db import get_db, now
from .models import (
    Audit,
    Credential,
    Notification,
    SavedView,
    Ticket,
    TicketDuplicate,
    TicketTag,
    User,
    Watcher,
)
from .security import identity, passwords, require_admin, staff, ticket_access, visible_query

router = APIRouter(prefix="/api")


def staff_only(user):
    if not staff(user):
        raise HTTPException(403, "Staff access required")


def audit(db, user, action, ticket_id=None, details=None):
    db.add(Audit(actor_id=user.id, action=action, ticket_id=ticket_id, details=details or {}))


def reset_target(db, user, target_id):
    target = db.get(User, target_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.automation:
        raise HTTPException(422, "Automation users use API keys, not interactive passwords")
    if target.id == user.id:
        raise HTTPException(422, "Use My account to change your own password")
    return target


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    data: s.PasswordReset,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = reset_target(db, user, user_id)
    if passwords.verify(data.temporary_password, target.password_hash):
        raise HTTPException(422, "Choose a different temporary password")
    target.password_hash = passwords.hash(data.temporary_password)
    target.must_change_password = True
    db.execute(delete(Credential).where(Credential.user_id == target.id))
    audit(db, user, "password_reset", details={"user_id": target.id})
    db.commit()
    return {"ok": True}


@router.post("/admin/users/{user_id}/require-password-change")
def require_password_change(
    user_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    target = reset_target(db, user, user_id)
    target.must_change_password = True
    db.execute(delete(Credential).where(Credential.user_id == target.id))
    audit(db, user, "password_change_required", details={"user_id": target.id})
    db.commit()
    return {"ok": True}


def notification_query(user):
    query = select(Notification).where(
        Notification.user_id == user.id,
        Notification.ticket_id.in_(visible_query(user).with_only_columns(Ticket.id)),
    )
    if not staff(user):
        query = query.where(Notification.internal.is_(False))
    return query


@router.get("/notifications")
def notifications(
    unread: bool = False,
    offset: int = 0,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    base = notification_query(user)
    unread_count = db.scalar(
        select(func.count()).select_from(base.where(Notification.read_at.is_(None)).subquery())
    )
    query = base.where(Notification.read_at.is_(None)) if unread else base
    items = db.scalars(
        query.order_by(Notification.id.desc()).offset(max(0, offset)).limit(50)
    ).all()
    return {
        "unread_count": unread_count,
        "items": [
            {
                "id": n.id,
                "ticket_id": n.ticket_id,
                "title": db.get(Ticket, n.ticket_id).title,
                "kind": n.kind,
                "created_at": n.created_at,
                "read_at": n.read_at,
            }
            for n in items
        ],
    }


@router.post("/notifications/read-all")
def read_all(user: User = Depends(identity), db: Session = Depends(get_db)):
    for item in db.scalars(notification_query(user).where(Notification.read_at.is_(None))):
        item.read_at = now()
    db.commit()
    return {"ok": True}


@router.patch("/notifications/{notification_id}")
def read_notification(
    notification_id: int, user: User = Depends(identity), db: Session = Depends(get_db)
):
    item = db.scalar(notification_query(user).where(Notification.id == notification_id))
    if not item:
        raise HTTPException(404, "Notification not found")
    item.read_at = now()
    db.commit()
    return {"ok": True}


@router.put("/tickets/{ticket_id}/watchers/{user_id}")
def watch(
    ticket_id: int, user_id: int, user: User = Depends(identity), db: Session = Depends(get_db)
):
    ticket = ticket_access(db, user, ticket_id)
    if user_id != user.id:
        staff_only(user)
    target = db.get(User, user_id)
    if (
        not target
        or not target.active
        or target.automation
        or not workspace.can_read(db, target, ticket_id)
    ):
        raise HTTPException(422, "Watcher must be an active human with access to this ticket")
    if not db.get(Watcher, (ticket_id, user_id)):
        db.add(Watcher(ticket_id=ticket_id, user_id=user_id))
        audit(db, user, "watcher_added", ticket_id, {"user_id": user_id})
        if user_id != user.id:
            workspace.add_notification(db, target, ticket, "watching")
    db.commit()
    return {"ok": True}


@router.delete("/tickets/{ticket_id}/watchers/{user_id}")
def unwatch(
    ticket_id: int, user_id: int, user: User = Depends(identity), db: Session = Depends(get_db)
):
    ticket_access(db, user, ticket_id)
    if user_id != user.id:
        staff_only(user)
    watcher = db.get(Watcher, (ticket_id, user_id))
    if watcher:
        db.delete(watcher)
        audit(db, user, "watcher_removed", ticket_id, {"user_id": user_id})
    db.commit()
    return {"ok": True}


@router.get("/attention")
def attention(
    reason: str = "",
    mine: bool = False,
    offset: int = 0,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    from .main import ticket_dict

    staff_only(user)
    if reason not in {"", "breached", "at_risk", "unanswered", "unassigned"}:
        raise HTTPException(422, "Unknown attention reason")
    query = visible_query(user).where(Ticket.status.not_in(["closed", "pending_approval"]))
    if mine:
        query = query.where(Ticket.assignee_id == user.id)
    items = []
    counts = dict.fromkeys(["breached", "at_risk", "unanswered", "unassigned"], 0)
    rank = {key: i for i, key in enumerate(counts)}
    for ticket in db.scalars(query.order_by(Ticket.created_at)):
        record = ticket_dict(db, ticket, user)
        for key in record["attention"]:
            counts[key] += 1
        if record["attention"] and (not reason or reason in record["attention"]):
            items.append(record)
    items.sort(
        key=lambda item: (min(rank[r] for r in item["attention"]), item["created_at"], item["id"])
    )
    return {
        "items": items[max(0, offset) : max(0, offset) + 100],
        "total": len(items),
        "counts": counts,
    }


@router.patch("/tickets/{ticket_id}/organization")
def organize(
    ticket_id: int,
    data: s.TicketOrganization,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    from .main import ticket_dict

    staff_only(user)
    # Serialize duplicate edits so simultaneous links cannot form a cycle.
    db.scalars(select(Ticket).order_by(Ticket.id).with_for_update()).all()
    ticket = ticket_access(db, user, ticket_id)
    if ticket.version != data.version:
        raise HTTPException(409, "This ticket changed. Refresh it and try again.")
    details = {}
    if data.tags is not None:
        db.execute(delete(TicketTag).where(TicketTag.ticket_id == ticket_id))
        db.add_all([TicketTag(ticket_id=ticket_id, name=name) for name in data.tags])
        details["tags"] = data.tags
    if "duplicate_of_id" in data.model_fields_set:
        target_id = data.duplicate_of_id
        if target_id:
            target = ticket_access(db, user, target_id)
            if target.kind != ticket.kind:
                raise HTTPException(422, "Duplicate links must connect the same kind of ticket")
            seen = {ticket_id}
            cursor = target_id
            while cursor:
                if cursor in seen:
                    raise HTTPException(422, "Duplicate links cannot form a cycle")
                seen.add(cursor)
                link = db.get(TicketDuplicate, cursor)
                cursor = link.duplicate_of_id if link else None
        link = db.get(TicketDuplicate, ticket_id)
        if link:
            db.delete(link)
            db.flush()
        if target_id:
            db.add(TicketDuplicate(ticket_id=ticket_id, duplicate_of_id=target_id))
        details["duplicate_of_id"] = target_id
    ticket.updated_at = now()
    audit(db, user, "organization_changed", ticket_id, details)
    if details:
        workspace.notify(db, ticket, user, "ticket_updated", internal=True)
    db.commit()
    return ticket_dict(db, ticket, user, True)


@router.post("/tickets/bulk")
def bulk(data: s.BulkUpdate, user: User = Depends(identity), db: Session = Depends(get_db)):
    from .main import apply_ticket_update, ticket_dict

    staff_only(user)
    refs = sorted(data.tickets, key=lambda t: t.id)
    for ref in refs:
        ticket = ticket_access(db, user, ref.id)
        if ticket.version != ref.version:
            raise HTTPException(409, f"Ticket #{ref.id} changed. No tickets were updated.")
    updates = data.model_dump(exclude={"tickets"}, exclude_unset=True)
    tickets = [
        apply_ticket_update(ref.id, s.TicketUpdate(version=ref.version, **updates), user, db)
        for ref in refs
    ]
    db.commit()
    return [ticket_dict(db, ticket, user) for ticket in tickets]


@router.get("/views")
def views(user: User = Depends(identity), db: Session = Depends(get_db)):
    return [
        {"id": v.id, "name": v.name, "config": v.config}
        for v in db.scalars(
            select(SavedView).where(SavedView.owner_id == user.id).order_by(SavedView.name)
        )
    ]


@router.post("/views", status_code=201)
def save_view(data: s.ViewInput, user: User = Depends(identity), db: Session = Depends(get_db)):
    if not staff(user) and (data.config.tag or data.config.kind == "bug"):
        raise HTTPException(403, "This view uses staff-only filters")
    view = SavedView(owner_id=user.id, name=data.name.strip(), config=data.config.model_dump())
    if not view.name:
        raise HTTPException(422, "Name the saved view")
    db.add(view)
    db.commit()
    return {"id": view.id, "name": view.name, "config": view.config}


@router.delete("/views/{view_id}")
def delete_view(view_id: int, user: User = Depends(identity), db: Session = Depends(get_db)):
    view = db.get(SavedView, view_id)
    if not view or view.owner_id != user.id:
        raise HTTPException(404, "View not found")
    db.delete(view)
    db.commit()
    return {"ok": True}
