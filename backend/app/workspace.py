"""Permission-aware subscriptions, notifications, and ticket organization."""

from sqlalchemy import select

from . import sla
from .models import (
    Cycle,
    Message,
    Notification,
    NotificationPreference,
    Ticket,
    TicketDuplicate,
    TicketTag,
    User,
    Watcher,
)
from .security import staff, visible_query


def can_read(db, user, ticket_id):
    return db.scalar(visible_query(user).where(Ticket.id == ticket_id)) is not None


def add_notification(db, recipient, ticket, kind, internal=False):
    preference = db.get(NotificationPreference, (recipient.id, kind))
    if not preference or preference.in_app:
        db.add(
            Notification(user_id=recipient.id, ticket_id=ticket.id, kind=kind, internal=internal)
        )
    from .mail import queue_delivery

    if not preference or preference.email:
        queue_delivery(db, recipient, ticket, kind, internal)


def notify(db, ticket, actor, kind, internal=False, extra_recipients=()):
    recipients = {ticket.creator_id, ticket.assignee_id, *extra_recipients}
    recipients.update(db.scalars(select(Watcher.user_id).where(Watcher.ticket_id == ticket.id)))
    recipients.discard(None)
    recipients.discard(actor.id)
    for recipient_id in sorted(recipients):
        recipient = db.get(User, recipient_id)
        if not recipient or not recipient.active or recipient.automation:
            continue
        if internal and not staff(recipient):
            continue
        if can_read(db, recipient, ticket.id):
            add_notification(db, recipient, ticket, kind, internal)


def confirm_creation(db, ticket, actor):
    """Email a human creator a receipt without adding a self-notification."""
    if actor.active and not actor.automation and actor.email:
        from .mail import queue_delivery

        queue_delivery(db, actor, ticket, "ticket_created", ticket.kind == "bug")


def notify_unassigned_staff_by_email(db, ticket, actor):
    from .mail import queue_delivery

    for recipient in db.scalars(select(User).where(User.active.is_(True))):
        if (
            recipient.id != actor.id
            and not recipient.automation
            and ("admin" in recipient.roles or "assigner" in recipient.roles)
        ):
            queue_delivery(db, recipient, ticket, "ticket_created", ticket.kind == "bug")


def organization(db, ticket, user):
    result = {"watching": db.get(Watcher, (ticket.id, user.id)) is not None}
    if staff(user):
        result["tags"] = list(
            db.scalars(
                select(TicketTag.name)
                .where(TicketTag.ticket_id == ticket.id)
                .order_by(TicketTag.name)
            )
        )
        duplicate = db.get(TicketDuplicate, ticket.id)
        result["duplicate_of_id"] = duplicate.duplicate_of_id if duplicate else None
        result["watchers"] = [
            {"id": u.id, "name": u.name}
            for u in db.scalars(
                select(User)
                .join(Watcher, Watcher.user_id == User.id)
                .where(Watcher.ticket_id == ticket.id)
            )
            if u.active and can_read(db, u, ticket.id)
        ]
    return result


def attention_reasons(db, ticket, summary=None):
    if ticket.status in {"closed", "pending_approval"}:
        return []
    reasons = []
    states = summary if summary is not None else sla.summary(db, ticket)
    active = [c for c in states if not c["completed_at"] and c["state"] != "cancelled"]
    if any(c["state"] == "breached" for c in active):
        reasons.append("breached")
    if any(c["state"] == "at_risk" for c in active):
        reasons.append("at_risk")
    if ticket.kind == "support" and ticket.status != "waiting_customer":
        first = db.scalar(
            select(Cycle).where(Cycle.ticket_id == ticket.id, Cycle.metric == "first_response")
        )
        messages = db.execute(
            select(Message, User)
            .join(User, Message.author_id == User.id)
            .where(Message.ticket_id == ticket.id, Message.internal.is_(False))
            .order_by(Message.created_at.desc(), Message.id.desc())
        ).all()
        last = next(((m, u) for m, u in messages if not (staff(u) and u.automation)), None)
        if (first and not first.completed_at) or (last and not staff(last[1])):
            reasons.append("unanswered")
    if ticket.assignee_id is None:
        reasons.append("unassigned")
    return reasons
