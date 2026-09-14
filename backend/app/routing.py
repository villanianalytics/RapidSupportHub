"""Configurable issue categories, support groups, and automatic assignment."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import schemas as s
from .db import get_db
from .models import (
    AssignmentRule,
    Audit,
    IssueCategory,
    SupportGroup,
    SupportGroupMember,
    Ticket,
    User,
)
from .security import require_admin, staff

router = APIRouter(prefix="/api/admin/routing", tags=["Assignment routing"])


def active_agent(db, user_id):
    user = db.get(User, user_id)
    if not user or not user.active or user.automation or not staff(user):
        raise HTTPException(422, "Support-group members must be active human staff")
    return user


def configuration(db):
    members = db.execute(
        select(SupportGroupMember.group_id, SupportGroupMember.user_id)
    ).all()
    by_group = {}
    for group_id, user_id in members:
        by_group.setdefault(group_id, []).append(user_id)
    rules = {rule.category_id: rule for rule in db.scalars(select(AssignmentRule))}
    return {
        "categories": [
            {
                "id": item.id,
                "name": item.name,
                "kind": item.kind,
                "incident_type": item.incident_type,
                "active": item.active,
            }
            for item in db.scalars(select(IssueCategory).order_by(IssueCategory.name))
        ],
        "groups": [
            {"id": item.id, "name": item.name, "user_ids": by_group.get(item.id, [])}
            for item in db.scalars(select(SupportGroup).order_by(SupportGroup.name))
        ],
        "rules": [
            {
                "category_id": category_id,
                "strategy": rule.strategy,
                "group_id": rule.group_id,
                "assignee_id": rule.assignee_id,
                "last_assigned_user_id": rule.last_assigned_user_id,
            }
            for category_id, rule in rules.items()
        ],
    }


@router.get("")
def get_configuration(user=Depends(require_admin), db: Session = Depends(get_db)):
    return configuration(db)


@router.post("/categories", status_code=201)
def create_category(
    data: s.CategoryInput, user=Depends(require_admin), db: Session = Depends(get_db)
):
    item = IssueCategory(**data.model_dump())
    db.add(item)
    db.add(Audit(actor_id=user.id, action="issue_category_created", details={"name": item.name}))
    db.commit()
    return configuration(db)


@router.patch("/categories/{category_id}")
def update_category(
    category_id: int,
    data: s.CategoryInput,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(IssueCategory, category_id)
    if not item:
        raise HTTPException(404, "Issue category not found")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    db.add(Audit(actor_id=user.id, action="issue_category_updated", details={"id": item.id}))
    db.commit()
    return configuration(db)


@router.post("/groups", status_code=201)
def create_group(data: s.Named, user=Depends(require_admin), db: Session = Depends(get_db)):
    item = SupportGroup(name=data.name.strip())
    db.add(item)
    db.add(Audit(actor_id=user.id, action="support_group_created", details={"name": item.name}))
    db.commit()
    return configuration(db)


@router.put("/groups/{group_id}/members")
def set_members(
    group_id: int,
    data: s.GroupMembers,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.get(SupportGroup, group_id):
        raise HTTPException(404, "Support group not found")
    ids = sorted(set(data.user_ids))
    for user_id in ids:
        active_agent(db, user_id)
    db.execute(delete(SupportGroupMember).where(SupportGroupMember.group_id == group_id))
    db.add_all([SupportGroupMember(group_id=group_id, user_id=user_id) for user_id in ids])
    db.add(
        Audit(
            actor_id=user.id,
            action="support_group_members_changed",
            details={"group_id": group_id, "user_ids": ids},
        )
    )
    db.commit()
    return configuration(db)


@router.put("/rules")
def save_rule(
    data: s.AssignmentRuleInput,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not db.get(IssueCategory, data.category_id):
        raise HTTPException(422, "Unknown issue category")
    if data.assignee_id:
        active_agent(db, data.assignee_id)
    if data.group_id and not db.get(SupportGroup, data.group_id):
        raise HTTPException(422, "Unknown support group")
    rule = db.get(AssignmentRule, data.category_id)
    if not rule:
        rule = AssignmentRule(category_id=data.category_id)
        db.add(rule)
    for key, value in data.model_dump().items():
        if key != "category_id":
            setattr(rule, key, value)
    db.add(
        Audit(
            actor_id=user.id,
            action="assignment_rule_saved",
            details=data.model_dump(),
        )
    )
    db.commit()
    return configuration(db)


def assign(db, ticket):
    rule = (
        db.scalar(
            select(AssignmentRule)
            .where(AssignmentRule.category_id == ticket.category_id)
            .with_for_update()
        )
        if ticket.category_id
        else None
    )
    if not rule or rule.strategy == "manual":
        return None
    if rule.strategy == "fixed":
        candidate = db.get(User, rule.assignee_id)
        return candidate.id if candidate and candidate.active and staff(candidate) else None
    members = [
        member
        for member in db.scalars(
            select(User)
            .join(SupportGroupMember, SupportGroupMember.user_id == User.id)
            .where(SupportGroupMember.group_id == rule.group_id, User.active.is_(True))
            .order_by(User.id)
        )
        if not member.automation and staff(member)
    ]
    if not members:
        return None
    if rule.strategy == "round_robin":
        after = [member for member in members if member.id > (rule.last_assigned_user_id or 0)]
        chosen = (after or members)[0]
        rule.last_assigned_user_id = chosen.id
        return chosen.id
    counts = dict(
        db.execute(
            select(Ticket.assignee_id, func.count())
            .where(
                Ticket.assignee_id.in_([member.id for member in members]),
                Ticket.status != "closed",
            )
            .group_by(Ticket.assignee_id)
        ).all()
    )
    return min(members, key=lambda member: (counts.get(member.id, 0), member.id)).id
