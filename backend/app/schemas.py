from datetime import date, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

Role = Literal["admin", "agent", "developer", "assigner", "customer_own", "customer_company"]
Severity = Literal["sev1", "sev2", "sev3", "sev4"]
Incident = Literal["outage", "bug", "question", "enhancement", "request"]
Status = Literal["new", "started", "in_progress", "waiting_customer", "pending_approval", "closed"]


class Login(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PasswordReset(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.@-]+$")
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=40)
    password: str = Field(min_length=12, max_length=256)
    roles: list[Role] = Field(min_length=1)
    company_id: int | None = None
    manage_reports: bool = False
    automation: bool = False


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    roles: list[Role] = Field(min_length=1)
    company_id: int | None = None
    manage_reports: bool = False
    active: bool = True


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["support", "bug", "both"] = "both"
    incident_type: Literal["outage", "bug", "question", "enhancement"] = "question"
    active: bool = True
    parent_id: int | None = None
    product_id: int


class IssueTypeInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    classification: Literal["outage", "bug", "question", "enhancement"] = "question"
    active: bool = True


class GroupMembers(BaseModel):
    user_ids: list[int] = Field(max_length=100)


class AssignmentRuleInput(BaseModel):
    category_id: int
    strategy: Literal["manual", "fixed", "round_robin", "least_open"]
    group_id: int | None = None
    assignee_id: int | None = None

    @model_validator(mode="after")
    def valid_target(self):
        if self.strategy == "fixed" and not self.assignee_id:
            raise ValueError("Fixed assignment requires an agent")
        if self.strategy in {"round_robin", "least_open"} and not self.group_id:
            raise ValueError("Group assignment requires a support group")
        return self


class Targets(BaseModel):
    severity: Severity
    incident_type: Literal["*", "outage", "bug", "question", "enhancement", "request"] = "*"
    first_response: int = Field(gt=0, le=525600)
    resolution: int = Field(gt=0, le=525600)
    reply: int | None = Field(default=None, gt=0, le=525600)
    update: int | None = Field(default=None, gt=0, le=525600)


class SLAConfig(BaseModel):
    timezone: str = "America/New_York"
    coverage: Literal["24x7", "business"] = "24x7"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    start: str = "09:00"
    end: str = "17:00"
    holidays: list[date] = Field(default_factory=list, max_length=366)
    pause_waiting: bool = True
    targets: list[Targets] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_calendar(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone")
        try:
            start, end = time.fromisoformat(self.start), time.fromisoformat(self.end)
        except ValueError:
            raise ValueError("Use HH:MM times")
        if start.tzinfo or end.tzinfo or start >= end:
            raise ValueError("Business hours must start before they end within one day")
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("Weekdays must be between 0 (Monday) and 6 (Sunday)")
        keys = [(t.severity, t.incident_type) for t in self.targets]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate severity / incident target")
        return self


class PolicyInput(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=160)
    config: SLAConfig


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(min_length=1, max_length=50000)
    kind: Literal["support", "bug"] = "support"
    incident_type: Incident = "question"
    severity: Severity = "sev3"
    company_id: int | None = None
    product_id: int
    category_id: int | None = None
    subcategory_id: int | None = None
    issue_type_id: int | None = None
    reproduction: str = Field(default="", max_length=20000)
    affected_version: str = Field(default="", max_length=100)


class TicketUpdate(BaseModel):
    version: int
    status: Status | None = None
    severity: Severity | None = None
    incident_type: Incident | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    issue_type_id: int | None = None
    assignee_id: int | None = None
    linked_bug_id: int | None = None
    resolution: str | None = Field(default=None, max_length=20000)
    reason: str = Field(default="", max_length=2000)


class TicketOrganization(BaseModel):
    version: int
    tags: list[str] | None = Field(default=None, max_length=12)
    duplicate_of_id: int | None = None

    @model_validator(mode="after")
    def clean_tags(self):
        if self.tags is not None:
            self.tags = sorted(set(t.strip().lower() for t in self.tags if t.strip()))
            if any(
                len(t) > 40 or any(not (c.isalnum() or c in "-_ ") for c in t) for t in self.tags
            ):
                raise ValueError(
                    "Tags must be at most 40 letters, numbers, spaces, hyphens or underscores"
                )
        return self


class TicketReference(BaseModel):
    id: int
    version: int


class BulkUpdate(BaseModel):
    tickets: list[TicketReference] = Field(min_length=1, max_length=100)
    status: Status | None = None
    assignee_id: int | None = None
    resolution: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def changes(self):
        if len({t.id for t in self.tickets}) != len(self.tickets):
            raise ValueError("Select each ticket only once")
        if self.status is None and "assignee_id" not in self.model_fields_set:
            raise ValueError("Choose an assignment or status change")
        return self


class ViewConfig(BaseModel):
    q: str = Field(default="", max_length=200)
    kind: Literal["", "support", "bug"] = ""
    status: Status | Literal[""] = ""
    mine: bool = False
    watching: bool = False
    severity: Severity | Literal[""] = ""
    product_id: int | None = None
    company_id: int | None = None
    tag: str = Field(default="", max_length=40)
    layout: Literal["list", "board"] = "list"


class ViewInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: ViewConfig


class MessageInput(BaseModel):
    body: str = Field(min_length=1, max_length=50000)
    internal: bool = False


class KeyInput(BaseModel):
    user_id: int
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["read", "write", "reports"]] = Field(min_length=1)
    expires_days: int = Field(default=90, ge=1, le=365)


class ReportConfig(BaseModel):
    view: Literal["summary", "records"] = "summary"
    columns: list[
        Literal[
            "id",
            "title",
            "description",
            "company",
            "product",
            "status",
            "severity",
            "incident_type",
            "assignee",
            "creator",
            "kind",
            "created_at",
            "updated_at",
            "resolution",
            "first_response_minutes",
            "resolution_minutes",
        ]
    ] = Field(
        default_factory=lambda: [
            "id",
            "title",
            "company",
            "product",
            "status",
            "severity",
            "assignee",
        ],
        min_length=1,
        max_length=16,
    )
    group_by: Literal[
        "status",
        "severity",
        "incident_type",
        "assignee",
        "first_response_agent",
        "company",
        "product",
        "kind",
    ] = "incident_type"
    metric: Literal["count", "first_response", "resolution", "reply", "update"] = "count"
    status: Status | None = None
    severity: Severity | None = None
    company_id: int | None = None
    product_id: int | None = None
    assignee_id: int | None = None
    kind: Literal["support", "bug"] | None = None
    incident_type: Incident | None = None
    from_date: date | None = None
    to_date: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("Start date must precede end date")
        return self


class ReportInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    shared: bool = False
    config: ReportConfig
