"""Administrator-managed Amazon SES SMTP readiness configuration."""

import os
import re
import smtplib
import ssl
from datetime import timedelta
from email.headerregistry import Address
from email.message import EmailMessage
from threading import Event, Thread

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db, now
from .entra import cipher
from .models import Audit, EmailDelivery, SMTPConfiguration, Ticket, User
from .security import require_admin, staff, visible_query

router = APIRouter(prefix="/api/admin/email", tags=["Email configuration"])
REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EVENTS = {
    "ticket_created": "created",
    "ticket_updated": "updated",
    "assigned": "assigned",
    "status_changed": "status changed",
    "approval_requested": "resolution ready for approval",
    "staff_reply": "support reply added",
    "customer_reply": "customer reply added",
    "private_note": "private note added",
    "attachment_added": "attachment added",
    "watching": "you were added as a watcher",
}


class SMTPInput(BaseModel):
    region: str = Field(min_length=8, max_length=30)
    port: int = Field(default=587)
    username: str = Field(min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=4096)
    from_email: str = Field(min_length=3, max_length=254)
    from_name: str = Field(default="RapidSupportHub", min_length=1, max_length=160)
    reply_to: str = Field(default="", max_length=254)
    enabled: bool = False

    @field_validator("region")
    @classmethod
    def valid_region(cls, value):
        value = value.strip().lower()
        if not REGION.fullmatch(value):
            raise ValueError("Use an AWS region such as us-east-1")
        return value

    @field_validator("port")
    @classmethod
    def valid_port(cls, value):
        if value not in {465, 587}:
            raise ValueError("Amazon SES SMTP supports port 465 or 587 here")
        return value

    @field_validator("from_email", "reply_to")
    @classmethod
    def valid_address(cls, value):
        value = value.strip()
        if not value:
            return value
        if not EMAIL.fullmatch(value) or any(ord(char) > 127 for char in value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("username", "from_name")
    @classmethod
    def safe_header(cls, value):
        value = value.strip()
        if "\r" in value or "\n" in value:
            raise ValueError("Line breaks are not allowed")
        return value


def endpoint(region):
    suffix = "amazonaws.com.cn" if region.startswith("cn-") else "amazonaws.com"
    return f"email-smtp.{region}.{suffix}"


def public(record):
    return {
        "region": record.region,
        "endpoint": endpoint(record.region),
        "port": record.port,
        "username": record.username,
        "from_email": record.from_email,
        "from_name": record.from_name,
        "reply_to": record.reply_to,
        "enabled": record.enabled,
        "has_password": bool(record.password_encrypted),
        "last_tested_at": record.last_tested_at,
        "last_test_ok": record.last_test_ok,
        "updated_at": record.updated_at,
    }


@router.get("")
def configuration(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        cipher()
        ready = True
    except HTTPException:
        ready = False
    record = db.get(SMTPConfiguration, 1)
    return {"server_ready": ready, "configuration": public(record) if record else None}


@router.put("")
def save(
    data: SMTPInput,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = db.get(SMTPConfiguration, 1, with_for_update=True)
    if not record and not data.password:
        raise HTTPException(422, "An Amazon SES SMTP password is required")
    encrypted = (
        cipher().encrypt(data.password.encode()).decode()
        if data.password
        else record.password_encrypted
    )
    values = data.model_dump(exclude={"password"})
    values.update(
        password_encrypted=encrypted,
        last_tested_at=None,
        last_test_ok=None,
        updated_at=now(),
    )
    if record:
        for key, value in values.items():
            setattr(record, key, value)
        action = "smtp_configuration_updated"
    else:
        record = SMTPConfiguration(id=1, **values)
        db.add(record)
        action = "smtp_configuration_created"
    db.add(
        Audit(
            actor_id=user.id,
            action=action,
            details={
                "region": record.region,
                "port": record.port,
                "from_email": record.from_email,
                "enabled": record.enabled,
                "password_rotated": bool(data.password),
            },
        )
    )
    db.commit()
    return public(record)


def verify_connection(record):
    host = endpoint(record.region)
    password = cipher().decrypt(record.password_encrypted.encode()).decode()
    context = ssl.create_default_context()
    if record.port == 465:
        connection = smtplib.SMTP_SSL(host, record.port, timeout=12, context=context)
    else:
        connection = smtplib.SMTP(host, record.port, timeout=12)
    with connection as smtp:
        smtp.ehlo()
        if record.port == 587:
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(record.username, password)


def queue_delivery(db, recipient, ticket, kind, internal=False):
    config = db.get(SMTPConfiguration, 1)
    if config and config.enabled and recipient.email:
        db.add(
            EmailDelivery(
                user_id=recipient.id,
                ticket_id=ticket.id,
                kind=kind,
                internal=internal,
            )
        )


def _message(config, recipient, ticket, kind):
    label = "Internal issue" if ticket.kind == "bug" else "Support ticket"
    event = EVENTS.get(kind, "updated")
    message = EmailMessage()
    message["From"] = Address(config.from_name, addr_spec=config.from_email)
    message["To"] = recipient.email
    if config.reply_to:
        message["Reply-To"] = config.reply_to
    message["Subject"] = f"[{label} #{ticket.id}] {event.capitalize()}: {ticket.title}"
    origin = os.getenv("APP_ORIGIN", "http://localhost:5173").rstrip("/")
    message.set_content(
        f"Hello {recipient.name},\n\n"
        f"{label} #{ticket.id} was {event}.\n\n"
        f"Title: {ticket.title}\nStatus: {ticket.status.replace('_', ' ').title()}\n"
        f"Severity: {ticket.severity.upper()}\n\nOpen RapidSupportHub: {origin}/\n\n"
        "This is an automated notification. Sign in to view the complete record."
    )
    return message


def _send(config, message):
    password = cipher().decrypt(config.password_encrypted.encode()).decode()
    context = ssl.create_default_context()
    connection = (
        smtplib.SMTP_SSL(endpoint(config.region), config.port, timeout=20, context=context)
        if config.port == 465
        else smtplib.SMTP(endpoint(config.region), config.port, timeout=20)
    )
    with connection as smtp:
        smtp.ehlo()
        if config.port == 587:
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(config.username, password)
        smtp.send_message(message)


def deliver_pending(limit=20):
    with SessionLocal() as db:
        config = db.get(SMTPConfiguration, 1)
        if not config or not config.enabled:
            return 0
        deliveries = db.scalars(
            select(EmailDelivery)
            .where(
                EmailDelivery.status.in_(["pending", "retrying"]),
                EmailDelivery.next_attempt_at <= now(),
            )
            .order_by(EmailDelivery.id)
            .limit(limit)
        ).all()
        for delivery in deliveries:
            recipient = db.get(User, delivery.user_id)
            ticket = db.get(Ticket, delivery.ticket_id)
            permitted = (
                recipient
                and ticket
                and recipient.active
                and not recipient.automation
                and recipient.email
                and (not delivery.internal or staff(recipient))
                and db.scalar(
                    visible_query(recipient).where(Ticket.id == delivery.ticket_id)
                )
                is not None
            )
            if not permitted:
                delivery.status = "suppressed"
                delivery.last_error = "Recipient no longer has access"
                db.commit()
                continue
            delivery.attempts += 1
            try:
                _send(config, _message(config, recipient, ticket, delivery.kind))
                delivery.status = "sent"
                delivery.sent_at = now()
                delivery.last_error = ""
            except (OSError, smtplib.SMTPException, ValueError, InvalidToken):
                delivery.last_error = "SMTP delivery failed"
                if delivery.attempts >= 6:
                    delivery.status = "failed"
                else:
                    delivery.status = "retrying"
                    delivery.next_attempt_at = now() + timedelta(
                        minutes=min(2 ** delivery.attempts, 60)
                    )
            db.commit()
        return len(deliveries)


def run_worker(stop):
    while not stop.wait(5):
        try:
            deliver_pending()
        except Exception:
            # A later cycle retries; the API must remain available if SMTP or the DB is transiently down.
            continue


def start_worker():
    stop = Event()
    thread = Thread(target=run_worker, args=(stop,), name="email-delivery", daemon=True)
    thread.start()
    return stop, thread


@router.get("/deliveries")
def delivery_status(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(EmailDelivery.status, func.count()).group_by(EmailDelivery.status)
        ).all()
    )
    recent = db.scalars(select(EmailDelivery).order_by(EmailDelivery.id.desc()).limit(20)).all()
    return {
        "counts": counts,
        "recent": [
            {
                "id": item.id,
                "ticket_id": item.ticket_id,
                "kind": item.kind,
                "status": item.status,
                "attempts": item.attempts,
                "created_at": item.created_at,
                "sent_at": item.sent_at,
            }
            for item in recent
        ],
    }


@router.post("/deliveries/retry")
def retry_failed(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    records = db.scalars(
        select(EmailDelivery).where(EmailDelivery.status == "failed")
    ).all()
    for item in records:
        item.status = "pending"
        item.attempts = 0
        item.next_attempt_at = now()
        item.last_error = ""
    db.add(
        Audit(
            actor_id=user.id,
            action="email_deliveries_retried",
            details={"count": len(records)},
        )
    )
    db.commit()
    return {"ok": True, "count": len(records)}


@router.post("/test")
def test_connection(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    record = db.get(SMTPConfiguration, 1, with_for_update=True)
    if not record:
        raise HTTPException(404, "Save Amazon SES SMTP settings first")
    try:
        verify_connection(record)
        ok, message = True, "Connected and authenticated successfully. No email was sent."
    except (OSError, smtplib.SMTPException, ValueError, InvalidToken) as exc:
        ok = False
        message = "Amazon SES rejected the connection or credentials. Check the region, port, and SMTP credentials."
        # The exception can contain a server response, so it is deliberately not returned or audited.
        _ = exc
    record.last_tested_at = now()
    record.last_test_ok = ok
    db.add(
        Audit(
            actor_id=user.id,
            action="smtp_connection_tested",
            details={"region": record.region, "port": record.port, "success": ok},
        )
    )
    db.commit()
    if not ok:
        raise HTTPException(422, message)
    return {"ok": True, "message": message, "tested_at": record.last_tested_at}
