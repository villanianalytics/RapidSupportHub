"""Administrator-managed Amazon SES SMTP readiness configuration."""

import re
import smtplib
import ssl

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .db import get_db, now
from .entra import cipher
from .models import Audit, SMTPConfiguration, User
from .security import require_admin

router = APIRouter(prefix="/api/admin/email", tags=["Email configuration"])
REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
