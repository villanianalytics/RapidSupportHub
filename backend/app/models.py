from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    manage_reports: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    automation: Mapped[bool] = mapped_column(Boolean, default=False)


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="Session")
    kind: Mapped[str] = mapped_column(String(20), default="session")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    config: Mapped[dict] = mapped_column(JSON)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="support")
    incident_type: Mapped[str] = mapped_column(String(30), default="question")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("issue_categories.id"), index=True)
    subcategory_id: Mapped[int | None] = mapped_column(
        ForeignKey("issue_categories.id"), index=True
    )
    issue_type_id: Mapped[int | None] = mapped_column(ForeignKey("issue_types.id"), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="sev3")
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    reproduction: Mapped[str] = mapped_column(Text, default="")
    affected_version: Mapped[str] = mapped_column(String(100), default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    linked_bug_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    sla_config: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Cycle(Base):
    __tablename__ = "sla_cycles"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    metric: Mapped[str] = mapped_column(String(30))
    target_minutes: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(160))
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON)


class Watcher(Base):
    __tablename__ = "ticket_watchers"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    internal: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    last_error: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class IssueCategory(Base):
    __tablename__ = "issue_categories"
    __table_args__ = (UniqueConstraint("product_id", "parent_id", "name", name="uq_issue_category_scope"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="both")
    incident_type: Mapped[str] = mapped_column(String(30), default="question")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("issue_categories.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)


class IssueType(Base):
    __tablename__ = "issue_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    classification: Mapped[str] = mapped_column(String(30), default="question")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupportGroup(Base):
    __tablename__ = "support_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class SupportGroupMember(Base):
    __tablename__ = "support_group_members"
    group_id: Mapped[int] = mapped_column(ForeignKey("support_groups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class AssignmentRule(Base):
    __tablename__ = "assignment_rules"
    category_id: Mapped[int] = mapped_column(ForeignKey("issue_categories.id"), primary_key=True)
    strategy: Mapped[str] = mapped_column(String(30), default="manual")
    group_id: Mapped[int | None] = mapped_column(ForeignKey("support_groups.id"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    last_assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class TicketTag(Base):
    __tablename__ = "ticket_tags"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), primary_key=True)


class TicketDuplicate(Base):
    __tablename__ = "ticket_duplicates"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    duplicate_of_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)


class SavedView(Base):
    __tablename__ = "saved_views"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict] = mapped_column(JSON)


class EntraConnection(Base):
    __tablename__ = "entra_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    tenant_id: Mapped[str] = mapped_column(String(36), unique=True)
    client_id: Mapped[str] = mapped_column(String(36))
    secret: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class EntraIdentity(Base):
    __tablename__ = "entra_identities"
    connection_id: Mapped[int] = mapped_column(ForeignKey("entra_connections.id"), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class EntraFlow(Base):
    __tablename__ = "entra_flows"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("entra_connections.id"))
    browser_digest: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(100))
    verifier: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class SMTPConfiguration(Base):
    __tablename__ = "smtp_configuration"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    region: Mapped[str] = mapped_column(String(30))
    port: Mapped[int] = mapped_column(Integer, default=587)
    username: Mapped[str] = mapped_column(String(255))
    password_encrypted: Mapped[str] = mapped_column(Text)
    from_email: Mapped[str] = mapped_column(String(254))
    from_name: Mapped[str] = mapped_column(String(160), default="RapidSupportHub")
    reply_to: Mapped[str] = mapped_column(String(254), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, index=True)
    actor: Mapped[str] = mapped_column(String(160), default="Anonymous")
    auth_method: Mapped[str] = mapped_column(String(20), default="anonymous")
    credential_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(160), index=True)
    resource: Mapped[str] = mapped_column(String(100), default="", index=True)
    resource_id: Mapped[str] = mapped_column(String(160), default="", index=True)
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    method: Mapped[str] = mapped_column(String(10), default="")
    route: Mapped[str] = mapped_column(String(200), default="")
    ip: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
