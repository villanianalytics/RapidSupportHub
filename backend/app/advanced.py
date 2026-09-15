"""Entitlements, configurable forms, queues, automation, preferences and releases."""

from datetime import datetime
from threading import Event, Thread
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import workspace
from .db import SessionLocal, get_db, now
from .models import (
    AgentAvailability,
    AssignmentRule,
    Audit,
    AutomationRule,
    Company,
    CompanyProduct,
    CustomField,
    IssueCategory,
    NotificationPreference,
    Product,
    ProductRelease,
    SupportGroup,
    SupportGroupMember,
    Ticket,
    TicketRelation,
    User,
)
from .security import identity, require_admin, staff, ticket_access

router = APIRouter(prefix="/api", tags=["Workspace controls"])


class Entitlements(BaseModel):
    product_ids: list[int] = Field(max_length=500)


class FieldInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    product_id: int
    category_id: int | None = None
    kind: Literal["support", "bug", "both"] = "both"
    field_type: Literal["text", "textarea", "number", "date", "select", "checkbox"] = "text"
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    active: bool = True


class AvailabilityInput(BaseModel):
    status: Literal["available", "busy", "away", "out_of_office"]
    until: datetime | None = None


class AutomationInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    active: bool = True
    trigger: Literal["created", "updated", "sla_risk", "inactive"] = "created"
    conditions: dict = Field(default_factory=dict)
    actions: dict = Field(default_factory=dict)


class PreferenceInput(BaseModel):
    event: Literal[
        "ticket_created",
        "ticket_updated",
        "assigned",
        "staff_reply",
        "customer_reply",
        "private_note",
        "release",
    ]
    in_app: bool = True
    email: bool = True


class ReleaseInput(BaseModel):
    product_id: int
    version: str = Field(min_length=1, max_length=100)
    status: Literal["planned", "in_progress", "released"] = "planned"
    notes: str = Field(default="", max_length=20000)


class RelationInput(BaseModel):
    target_id: int
    relation: Literal["related", "blocks", "caused_by", "duplicates"] = "related"


def audit(db, user, action, details):
    db.add(Audit(actor_id=user.id, action=action, details=details))


def validate_automation(db, data):
    condition_keys = {
        "product_id",
        "company_id",
        "severity",
        "category_id",
        "status",
        "inactive_minutes",
    }
    action_keys = {"assignee_id", "severity", "status"}
    if set(data.conditions) - condition_keys or set(data.actions) - action_keys:
        raise HTTPException(422, "Automation contains an unsupported condition or action")
    if "severity" in data.actions and data.actions["severity"] not in {
        "sev1",
        "sev2",
        "sev3",
        "sev4",
    }:
        raise HTTPException(422, "Invalid automation severity")
    if "status" in data.actions and data.actions["status"] not in {
        "new",
        "started",
        "in_progress",
        "waiting_customer",
    }:
        raise HTTPException(422, "Automation cannot resolve or close tickets")
    if data.actions.get("assignee_id"):
        target = db.get(User, data.actions["assignee_id"])
        if not target or not target.active or not staff(target):
            raise HTTPException(422, "Automation assignee must be active staff")


def field_dict(item):
    return {
        key: getattr(item, key)
        for key in (
            "id",
            "name",
            "product_id",
            "category_id",
            "kind",
            "field_type",
            "required",
            "options",
            "active",
        )
    }


@router.get("/admin/workspace-controls")
def controls(user=Depends(require_admin), db: Session = Depends(get_db)):
    entitlements = {}
    for company_id, product_id in db.execute(
        select(CompanyProduct.company_id, CompanyProduct.product_id)
    ):
        entitlements.setdefault(company_id, []).append(product_id)
    availability = {
        a.user_id: {"status": a.status, "until": a.until}
        for a in db.scalars(select(AgentAvailability))
    }
    return {
        "entitlements": entitlements,
        "fields": [
            field_dict(f)
            for f in db.scalars(
                select(CustomField).order_by(CustomField.product_id, CustomField.name)
            )
        ],
        "availability": availability,
        "automations": [
            {
                "id": r.id,
                "name": r.name,
                "active": r.active,
                "trigger": r.trigger,
                "conditions": r.conditions,
                "actions": r.actions,
            }
            for r in db.scalars(select(AutomationRule).order_by(AutomationRule.name))
        ],
        "releases": [
            {
                "id": r.id,
                "product_id": r.product_id,
                "version": r.version,
                "status": r.status,
                "notes": r.notes,
                "released_at": r.released_at,
            }
            for r in db.scalars(select(ProductRelease).order_by(ProductRelease.id.desc()))
        ],
    }


@router.get("/queues")
def queues(user=Depends(identity), db: Session = Depends(get_db)):
    if not staff(user):
        raise HTTPException(403, "Staff access required")
    groups = list(db.scalars(select(SupportGroup).order_by(SupportGroup.name)))
    result = []
    for group in groups:
        categories = list(
            db.scalars(
                select(AssignmentRule.category_id).where(AssignmentRule.group_id == group.id)
            )
        )
        open_count = (
            db.scalar(
                select(func.count())
                .select_from(Ticket)
                .where(
                    Ticket.status != "closed",
                    (Ticket.category_id.in_(categories) | Ticket.subcategory_id.in_(categories)),
                )
            )
            if categories
            else 0
        )
        result.append(
            {
                "id": group.id,
                "name": group.name,
                "open_count": open_count,
                "member_ids": list(
                    db.scalars(
                        select(SupportGroupMember.user_id).where(
                            SupportGroupMember.group_id == group.id
                        )
                    )
                ),
            }
        )
    return result


@router.put("/admin/companies/{company_id}/products")
def set_entitlements(
    company_id: int, data: Entitlements, user=Depends(require_admin), db: Session = Depends(get_db)
):
    if not db.get(Company, company_id):
        raise HTTPException(404, "Company not found")
    ids = sorted(set(data.product_ids))
    if len(ids) != db.scalar(select(func.count()).select_from(Product).where(Product.id.in_(ids))):
        raise HTTPException(422, "Unknown product")
    db.execute(delete(CompanyProduct).where(CompanyProduct.company_id == company_id))
    db.add_all([CompanyProduct(company_id=company_id, product_id=i) for i in ids])
    audit(
        db, user, "company_product_access_changed", {"company_id": company_id, "product_ids": ids}
    )
    db.commit()
    return {"company_id": company_id, "product_ids": ids}


@router.post("/admin/custom-fields", status_code=201)
def create_field(data: FieldInput, user=Depends(require_admin), db: Session = Depends(get_db)):
    if not db.get(Product, data.product_id):
        raise HTTPException(422, "Unknown product")
    if data.category_id:
        category = db.get(IssueCategory, data.category_id)
        if not category or category.product_id != data.product_id:
            raise HTTPException(422, "Category must belong to the product")
    if data.field_type == "select" and not data.options:
        raise HTTPException(422, "Select fields require options")
    item = CustomField(**data.model_dump())
    db.add(item)
    db.flush()
    audit(db, user, "custom_field_created", {"id": item.id, "name": item.name})
    db.commit()
    return field_dict(item)


@router.patch("/admin/custom-fields/{field_id}")
def update_field(
    field_id: int, data: FieldInput, user=Depends(require_admin), db: Session = Depends(get_db)
):
    item = db.get(CustomField, field_id)
    if not item:
        raise HTTPException(404, "Custom field not found")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    audit(db, user, "custom_field_updated", {"id": item.id})
    db.commit()
    return field_dict(item)


@router.put("/availability/{user_id}")
def set_availability(
    user_id: int, data: AvailabilityInput, user=Depends(identity), db: Session = Depends(get_db)
):
    if user_id != user.id and "admin" not in user.roles:
        raise HTTPException(403, "Administrator access required")
    target = db.get(User, user_id)
    if not target or not staff(target):
        raise HTTPException(422, "Availability applies to staff")
    item = db.get(AgentAvailability, user_id) or AgentAvailability(user_id=user_id)
    item.status, item.until = data.status, data.until
    db.add(item)
    audit(db, user, "availability_changed", {"user_id": user_id, "status": data.status})
    db.commit()
    return {"user_id": user_id, "status": item.status, "until": item.until}


@router.post("/admin/automations", status_code=201)
def create_automation(
    data: AutomationInput, user=Depends(require_admin), db: Session = Depends(get_db)
):
    validate_automation(db, data)
    item = AutomationRule(**data.model_dump())
    db.add(item)
    db.flush()
    audit(db, user, "automation_created", {"id": item.id})
    db.commit()
    return {"id": item.id}


@router.patch("/admin/automations/{rule_id}")
def update_automation(
    rule_id: int, data: AutomationInput, user=Depends(require_admin), db: Session = Depends(get_db)
):
    validate_automation(db, data)
    item = db.get(AutomationRule, rule_id)
    if not item:
        raise HTTPException(404, "Automation not found")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    audit(db, user, "automation_updated", {"id": item.id})
    db.commit()
    return {"id": item.id}


@router.get("/preferences")
def preferences(user=Depends(identity), db: Session = Depends(get_db)):
    return [
        {"event": p.event, "in_app": p.in_app, "email": p.email}
        for p in db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == user.id)
        )
    ]


@router.put("/preferences")
def set_preference(data: PreferenceInput, user=Depends(identity), db: Session = Depends(get_db)):
    item = db.get(NotificationPreference, (user.id, data.event)) or NotificationPreference(
        user_id=user.id, event=data.event
    )
    item.in_app, item.email = data.in_app, data.email
    db.add(item)
    db.commit()
    return data


@router.post("/admin/releases", status_code=201)
def create_release(data: ReleaseInput, user=Depends(require_admin), db: Session = Depends(get_db)):
    if not db.get(Product, data.product_id):
        raise HTTPException(422, "Unknown product")
    item = ProductRelease(
        **data.model_dump(), released_at=now() if data.status == "released" else None
    )
    db.add(item)
    db.flush()
    audit(db, user, "release_created", {"id": item.id, "version": item.version})
    db.commit()
    return {"id": item.id}


@router.patch("/admin/releases/{release_id}")
def update_release(
    release_id: int, data: ReleaseInput, user=Depends(require_admin), db: Session = Depends(get_db)
):
    item = db.get(ProductRelease, release_id)
    if not item:
        raise HTTPException(404, "Release not found")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    if data.status == "released" and not item.released_at:
        item.released_at = now()
    if data.status == "released":
        for ticket in db.scalars(select(Ticket).where(Ticket.fixed_release_id == item.id)):
            if ticket.kind == "support":
                from .models import Message

                body = f"Released in version {item.version}."
                if item.notes.strip():
                    body += "\n\n" + item.notes.strip()
                db.add(Message(ticket_id=ticket.id, author_id=user.id, body=body, internal=False))
            workspace.notify(db, ticket, user, "release", internal=ticket.kind == "bug")
    audit(db, user, "release_updated", {"id": item.id, "status": item.status})
    db.commit()
    return {"id": item.id}


@router.post("/tickets/{ticket_id}/relations", status_code=201)
def add_relation(
    ticket_id: int, data: RelationInput, user=Depends(identity), db: Session = Depends(get_db)
):
    if not staff(user):
        raise HTTPException(403, "Staff access required")
    source = ticket_access(db, user, ticket_id)
    target = ticket_access(db, user, data.target_id)
    if source.id == target.id:
        raise HTTPException(422, "A ticket cannot link to itself")
    item = TicketRelation(source_id=source.id, target_id=target.id, relation=data.relation)
    db.merge(item)
    audit(
        db,
        user,
        "ticket_relation_added",
        {"source_id": source.id, "target_id": target.id, "relation": data.relation},
    )
    db.commit()
    return {"ok": True}


@router.delete("/tickets/{ticket_id}/relations/{target_id}/{relation}")
def remove_relation(
    ticket_id: int,
    target_id: int,
    relation: str,
    user=Depends(identity),
    db: Session = Depends(get_db),
):
    if not staff(user):
        raise HTTPException(403, "Staff access required")
    ticket_access(db, user, ticket_id)
    item = db.get(TicketRelation, (ticket_id, target_id, relation))
    if item:
        db.delete(item)
        audit(
            db,
            user,
            "ticket_relation_removed",
            {"source_id": ticket_id, "target_id": target_id, "relation": relation},
        )
        db.commit()
    return {"ok": True}


def apply_automations(db, ticket, trigger, rule_id=None):
    """Apply deterministic, bounded rule actions during a ticket transaction."""
    query = select(AutomationRule)
    if rule_id is not None:
        query = query.where(AutomationRule.id == rule_id)
    for rule in db.scalars(
        query.where(AutomationRule.active.is_(True), AutomationRule.trigger == trigger).order_by(
            AutomationRule.id
        )
    ):
        c = rule.conditions or {}
        if any(
            (key == "product_id" and ticket.product_id != value)
            or (key == "company_id" and ticket.company_id != value)
            or (key == "severity" and ticket.severity != value)
            or (key == "category_id" and ticket.category_id != value)
            or (key == "status" and ticket.status != value)
            for key, value in c.items()
        ):
            continue
        actions = rule.actions or {}
        changed = False
        if actions.get("assignee_id"):
            changed |= ticket.assignee_id != actions["assignee_id"]
            ticket.assignee_id = actions["assignee_id"]
        if actions.get("severity"):
            changed |= ticket.severity != actions["severity"]
            ticket.severity = actions["severity"]
        if actions.get("status"):
            changed |= ticket.status != actions["status"]
            ticket.status = actions["status"]
        if changed:
            ticket.updated_at = now()
            db.add(
                Audit(
                    actor_id=ticket.creator_id,
                    ticket_id=ticket.id,
                    action="automation_applied",
                    details={"rule_id": rule.id, "name": rule.name},
                )
            )


def start_automation_worker():
    """Evaluate inactivity and SLA-risk rules without requiring a page request."""
    stop = Event()

    def run():
        from . import sla

        while not stop.wait(60):
            with SessionLocal() as db:
                scheduled = list(
                    db.scalars(
                        select(AutomationRule).where(
                            AutomationRule.active.is_(True),
                            AutomationRule.trigger.in_(["inactive", "sla_risk"]),
                        )
                    )
                )
                if not scheduled:
                    continue
                for ticket in db.scalars(select(Ticket).where(Ticket.status != "closed")):
                    for rule in scheduled:
                        if rule.trigger == "inactive":
                            minutes = int((rule.conditions or {}).get("inactive_minutes", 1440))
                            if (now() - ticket.updated_at).total_seconds() < minutes * 60:
                                continue
                        else:
                            if not any(
                                c["state"] in {"at_risk", "breached"}
                                for c in sla.summary(db, ticket)
                            ):
                                continue
                        apply_automations(db, ticket, rule.trigger, rule.id)
                db.commit()

    thread = Thread(target=run, name="rsh-automation", daemon=True)
    thread.start()
    return stop, thread
