import csv
import io
import math
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from . import auditing, sla, workspace
from . import schemas as s
from .db import Base, SessionLocal, engine, get_db, now
from .entra import router as entra_router
from .mail import router as mail_router
from .mail import start_worker
from .models import (
    Attachment,
    Audit,
    Company,
    Credential,
    IssueCategory,
    IssueType,
    Message,
    Policy,
    Product,
    Report,
    Ticket,
    TicketTag,
    User,
    Watcher,
)
from .operations import router as operations_router
from .routing import assign as assign_ticket
from .routing import router as routing_router
from .security import (
    admin,
    identity,
    issue,
    passwords,
    require_admin,
    staff,
    ticket_access,
    visible_query,
)


def seed_product_categories(db, product_id):
    for name in ("Application", "Data", "Business Rule", "Report"):
        exists = db.scalar(
            select(IssueCategory).where(
                IssueCategory.product_id == product_id,
                IssueCategory.parent_id.is_(None),
                IssueCategory.name == name,
            )
        )
        if not exists:
            db.add(IssueCategory(name=name, kind="both", active=True, product_id=product_id))


def seed_issue_types(db):
    defaults = (("Bug", "bug"), ("Question", "question"), ("Enhancement", "enhancement"))
    for name, classification in defaults:
        if not db.scalar(select(IssueType).where(IssueType.name == name)):
            db.add(IssueType(name=name, classification=classification, active=True))


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    columns = inspect(engine).get_columns("users")
    if "phone" not in {column["name"] for column in columns}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(40) NOT NULL DEFAULT ''"))
    columns = inspect(engine).get_columns("tickets")
    if "category_id" not in {column["name"] for column in columns}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE tickets ADD COLUMN category_id INTEGER"))
    ticket_columns = {column["name"] for column in inspect(engine).get_columns("tickets")}
    with engine.begin() as connection:
        if "subcategory_id" not in ticket_columns:
            connection.execute(text("ALTER TABLE tickets ADD COLUMN subcategory_id INTEGER"))
        if "issue_type_id" not in ticket_columns:
            connection.execute(text("ALTER TABLE tickets ADD COLUMN issue_type_id INTEGER"))
    columns = inspect(engine).get_columns("issue_categories")
    if "parent_id" not in {column["name"] for column in columns}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE issue_categories ADD COLUMN parent_id INTEGER"))
    if "product_id" not in {column["name"] for column in inspect(engine).get_columns("issue_categories")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE issue_categories ADD COLUMN product_id INTEGER"))
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE issue_categories DROP CONSTRAINT IF EXISTS issue_categories_name_key"))
    with SessionLocal() as db:
        auditing.initialize(db)
        if not db.scalar(select(User).limit(1)):
            initial = os.getenv("ADMIN_PASSWORD")
            if not initial or len(initial) < 12:
                raise RuntimeError(
                    "Set ADMIN_PASSWORD (at least 12 characters) to seed the first administrator"
                )
            db.add(
                User(
                    username="SupportAdmin",
                    name="Support Administrator",
                    email=os.getenv("ADMIN_EMAIL", ""),
                    password_hash=passwords.hash(initial),
                    roles=["admin"],
                    manage_reports=True,
                )
            )
            db.commit()
        seed_issue_types(db)
        db.flush()
        for product in db.scalars(select(Product)):
            seed_product_categories(db, product.id)
        if db.new or db.dirty:
            db.commit()
    worker = None
    if os.getenv("EMAIL_WORKER_ENABLED", "true").lower() == "true":
        worker = start_worker()
    try:
        yield
    finally:
        if worker:
            stop, thread = worker
            stop.set()
            thread.join(timeout=6)


app = FastAPI(
    title="RapidSupportHub API",
    dependencies=[Depends(auditing.bind_request)],
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("APP_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)
app.middleware("http")(auditing.middleware)
app.include_router(auditing.router)
app.include_router(operations_router)
app.include_router(entra_router)
app.include_router(mail_router)
app.include_router(routing_router)


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return JSONResponse(
        status_code=409,
        content={
            "detail": "A record with that value already exists, or a referenced record is unavailable"
        },
    )


@app.exception_handler(StaleDataError)
async def stale_error(request, exc):
    return JSONResponse(
        status_code=409,
        content={"detail": "This ticket changed. Refresh it and try again."},
    )


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


def audit(db, user, action, ticket=None, details=None, at=None):
    db.add(
        Audit(
            actor_id=user.id,
            ticket_id=ticket.id if ticket else None,
            action=action,
            details=details or {},
            created_at=at or now(),
        )
    )


def user_dict(user):
    return {
        k: getattr(user, k)
        for k in [
            "id",
            "username",
            "name",
            "email",
            "phone",
            "roles",
            "company_id",
            "manage_reports",
            "must_change_password",
            "active",
            "automation",
        ]
    }


def require_reports(user):
    if not (admin(user) or user.manage_reports):
        raise HTTPException(403, "Manage reports permission required")


def exists(db, model, record_id, label):
    if record_id is not None and not db.get(model, record_id):
        raise HTTPException(422, f"Unknown {label}")


def validate_assignee(db, record_id):
    if record_id is not None:
        assignee = db.get(User, record_id)
        if not assignee or not assignee.active or not staff(assignee):
            raise HTTPException(422, "Assignee must be an active staff member")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": "0.3.0"}


attempts = defaultdict(deque)
attempt_lock = Lock()
dummy_hash = passwords.hash(secrets.token_urlsafe(24))


def check_login_rate(request):
    ip = request.client.host if request.client else "unknown"
    stamp = time.monotonic()
    with attempt_lock:
        for key in list(attempts):
            while attempts[key] and attempts[key][0] < stamp - 300:
                attempts[key].popleft()
            if not attempts[key]:
                del attempts[key]
        if len(attempts[ip]) >= 15:
            raise HTTPException(429, "Too many sign-in attempts; retry in five minutes")
        attempts[ip].append(stamp)


@app.post("/api/auth/login")
def login(data: s.Login, request: Request, response: Response, db: Session = Depends(get_db)):
    if auditing.context.get() is not None:
        auditing.context.get()["attempted_username"] = data.username[:100]
    check_login_rate(request)
    user = db.scalar(select(User).where(User.username == data.username))
    valid = passwords.verify(data.password, user.password_hash if user else dummy_hash)
    if not user or not valid or not user.active or user.automation:
        raise HTTPException(401, "Invalid username or password")
    db.execute(delete(Credential).where(Credential.expires_at < now()))
    auditing.actor(user)
    raw, credential = issue(db, user)
    auditing.actor(user, credential)
    audit(db, user, "signed_in")
    db.commit()
    response.set_cookie(
        "rsh_session",
        raw,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="strict",
        max_age=43200,
        path="/api",
    )
    return user_dict(user)


@app.get("/api/auth/me")
def me(request: Request, user: User = Depends(identity)):
    result = user_dict(user)
    result["auth_method"] = "entra" if request.state.credential.kind == "sso" else "local"
    if request.state.credential.kind == "sso":
        result["must_change_password"] = False
    return result


@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    db.delete(request.state.credential)
    db.commit()
    response.delete_cookie("rsh_session", path="/api")
    return {"ok": True}


@app.post("/api/auth/password")
def change_password(
    data: s.PasswordChange,
    request: Request,
    response: Response,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    if request.state.credential.kind == "sso":
        raise HTTPException(422, "Manage your Microsoft password through your organization")
    if not passwords.verify(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if passwords.verify(data.new_password, user.password_hash):
        raise HTTPException(422, "Choose a different password")
    user.password_hash = passwords.hash(data.new_password)
    user.must_change_password = False
    db.execute(delete(Credential).where(Credential.user_id == user.id))
    raw, _ = issue(db, user)
    audit(db, user, "password_changed")
    db.commit()
    response.set_cookie(
        "rsh_session",
        raw,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="strict",
        max_age=43200,
        path="/api",
    )
    return user_dict(user)


@app.get("/api/catalog")
def catalog(user: User = Depends(identity), db: Session = Depends(get_db)):
    companies = db.scalars(
        select(Company) if staff(user) else select(Company).where(Company.id == user.company_id)
    ).all()
    users = db.scalars(select(User).where(User.active.is_(True))).all() if staff(user) else []
    return {
        "products": [
            {"id": p.id, "name": p.name, "description": p.description}
            for p in db.scalars(select(Product).order_by(Product.name))
        ],
        "companies": [{"id": c.id, "name": c.name} for c in companies],
        "agents": [{"id": u.id, "name": u.name} for u in users if staff(u)],
        "issue_types": [
            {"id": item.id, "name": item.name, "classification": item.classification}
            for item in db.scalars(select(IssueType).where(IssueType.active.is_(True)).order_by(IssueType.name))
        ],
        "categories": [
            {
                "id": item.id,
                "name": item.name,
                "kind": item.kind,
                "incident_type": item.incident_type,
                "parent_id": item.parent_id,
                "product_id": item.product_id,
                "display_name": (
                    f"{db.get(IssueCategory, item.parent_id).name} › {item.name}"
                    if item.parent_id
                    else item.name
                ),
            }
            for item in db.scalars(
                select(IssueCategory)
                .where(IssueCategory.active.is_(True), IssueCategory.product_id.is_not(None))
                .order_by(IssueCategory.name)
            )
        ],
    }


@app.get("/api/admin/users")
def users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_dict(u) for u in db.scalars(select(User).order_by(User.name))]


def validate_roles(db, roles, company_id):
    exists(db, Company, company_id, "company")
    if any(r.startswith("customer_") for r in roles) and not company_id:
        raise HTTPException(422, "Customer users must belong to a company")
    if any(r.startswith("customer_") for r in roles) and any(
        r in {"admin", "agent", "developer"} for r in roles
    ):
        raise HTTPException(422, "Use a separate account for customer and staff access")
    if "assigner" in roles and not any(role in {"admin", "agent", "developer"} for role in roles):
        raise HTTPException(422, "Assigner permission must accompany a staff role")


@app.post("/api/admin/users", status_code=201)
def create_user(
    data: s.UserCreate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    validate_roles(db, data.roles, data.company_id)
    record = User(
        **data.model_dump(exclude={"password"}),
        password_hash=passwords.hash(data.password),
        must_change_password=not data.automation,
    )
    db.add(record)
    db.flush()
    audit(db, user, "user_created", details={"user_id": record.id, "roles": record.roles})
    db.commit()
    return user_dict(record)


@app.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: int,
    data: s.UserUpdate,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = db.get(User, user_id)
    if not record:
        raise HTTPException(404, "User not found")
    if user_id == user.id and (not data.active or "admin" not in data.roles):
        raise HTTPException(422, "You cannot disable or remove your own administrator access")
    validate_roles(db, data.roles, data.company_id)
    for k, v in data.model_dump().items():
        if k not in {"name", "email", "phone"} or v is not None:
            setattr(record, k, v)
    keep = request.state.credential.id if user_id == user.id else -1
    db.execute(delete(Credential).where(Credential.user_id == user_id, Credential.id != keep))
    audit(
        db,
        user,
        "user_permissions_changed",
        details={"user_id": user_id, **data.model_dump()},
    )
    db.commit()
    return user_dict(record)


@app.post("/api/admin/companies", status_code=201)
def create_company(
    data: s.Named, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    company = Company(name=data.name.strip())
    db.add(company)
    audit(db, user, "company_created", details={"name": company.name})
    db.commit()
    return {"id": company.id, "name": company.name}


@app.post("/api/admin/products", status_code=201)
def create_product(
    data: s.Named, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    product = Product(name=data.name.strip(), description=data.description)
    db.add(product)
    db.flush()
    seed_issue_types(db)
    seed_product_categories(db, product.id)
    audit(db, user, "product_created", details={"name": product.name})
    db.commit()
    return {"id": product.id, "name": product.name}


@app.get("/api/admin/policies")
def policies(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [
        {"id": p.id, "company_id": p.company_id, "name": p.name, "config": p.config}
        for p in db.scalars(select(Policy))
    ]


@app.put("/api/admin/policies")
def save_policy(
    data: s.PolicyInput,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    exists(db, Company, data.company_id, "company")
    policy = db.scalar(select(Policy).where(Policy.company_id == data.company_id))
    if not policy:
        policy = Policy(company_id=data.company_id)
        db.add(policy)
    policy.name, policy.config = data.name, data.config.model_dump(mode="json")
    audit(db, user, "sla_policy_saved", details=data.model_dump(mode="json"))
    db.commit()
    return {
        "id": policy.id,
        "company_id": policy.company_id,
        "name": policy.name,
        "config": policy.config,
    }


@app.get("/api/admin/keys")
def keys(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [
        {
            "id": k.id,
            "user_id": k.user_id,
            "name": k.name,
            "scopes": k.scopes,
            "expires_at": k.expires_at,
        }
        for k in db.scalars(select(Credential).where(Credential.kind == "api"))
    ]


@app.post("/api/admin/keys", status_code=201)
def create_key(
    data: s.KeyInput, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    target = db.get(User, data.user_id)
    if not target or not target.active or not target.automation:
        raise HTTPException(422, "Select an active automation user")
    raw, key = issue(db, target, "api", data.name, data.scopes, data.expires_days)
    audit(
        db,
        user,
        "api_key_created",
        details={"credential_id": key.id, "user_id": target.id, "scopes": data.scopes},
    )
    db.commit()
    return {"id": key.id, "token": raw, "expires_at": key.expires_at}


@app.delete("/api/admin/keys/{key_id}")
def revoke_key(key_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    key = db.get(Credential, key_id)
    if not key or key.kind != "api":
        raise HTTPException(404, "Key not found")
    db.delete(key)
    audit(db, user, "api_key_revoked", details={"credential_id": key_id})
    db.commit()
    return {"ok": True}


def ticket_dict(db, ticket, user, detail=False):
    fields = [
        "id",
        "title",
        "description",
        "kind",
        "incident_type",
        "severity",
        "status",
        "company_id",
        "product_id",
        "creator_id",
        "assignee_id",
        "resolution",
        "created_at",
        "updated_at",
        "version",
    ]
    if staff(user):
        fields += ["reproduction", "affected_version", "linked_bug_id"]
    fields += ["category_id", "subcategory_id", "issue_type_id"]
    result = {k: getattr(ticket, k) for k in fields}
    result.update(workspace.organization(db, ticket, user))
    creator = db.get(User, ticket.creator_id)
    result["creator"] = creator.name
    if staff(user) or creator.id == user.id:
        result["submitter"] = {
            "id": creator.id,
            "name": creator.name,
            "email": creator.email,
            "phone": creator.phone,
        }
    result["assignee"] = (
        db.get(User, ticket.assignee_id).name if ticket.assignee_id else "Unassigned"
    )
    result["product"] = db.get(Product, ticket.product_id).name
    result["company"] = db.get(Company, ticket.company_id).name if ticket.company_id else "Internal"
    category = db.get(IssueCategory, ticket.category_id) if ticket.category_id else None
    subcategory = db.get(IssueCategory, ticket.subcategory_id) if ticket.subcategory_id else None
    issue_type = db.get(IssueType, ticket.issue_type_id) if ticket.issue_type_id else None
    result["category"] = category.name if category else "Legacy / uncategorized"
    result["subcategory"] = subcategory.name if subcategory else ""
    result["issue_type"] = issue_type.name if issue_type else ticket.incident_type.replace("_", " ").title()
    if staff(user):
        result["sla"] = sla.summary(db, ticket)
        result["attention"] = workspace.attention_reasons(db, ticket, result["sla"])
    if detail:
        result["messages"] = [
            {
                "id": m.id,
                "author": db.get(User, m.author_id).name,
                "body": m.body,
                "internal": m.internal,
                "created_at": m.created_at,
            }
            for m in db.scalars(
                select(Message).where(Message.ticket_id == ticket.id).order_by(Message.id)
            )
            if staff(user) or not m.internal
        ]
        result["attachments"] = [
            {"id": a.id, "filename": a.filename, "size": a.size, "internal": a.internal}
            for a in db.scalars(select(Attachment).where(Attachment.ticket_id == ticket.id))
            if staff(user) or not a.internal
        ]
        if staff(user):
            result["audit"] = [
                {
                    "id": a.id,
                    "actor": db.get(User, a.actor_id).name,
                    "action": a.action,
                    "details": a.details,
                    "created_at": a.created_at,
                }
                for a in db.scalars(
                    select(Audit).where(Audit.ticket_id == ticket.id).order_by(Audit.id.desc())
                )
            ]
    return result


@app.get("/api/tickets")
def list_tickets(
    q: str = "",
    kind: str | None = None,
    status: str | None = None,
    mine: bool = False,
    watching: bool = False,
    severity: str = "",
    product_id: int | None = None,
    company_id: int | None = None,
    tag: str = "",
    limit: int = 100,
    offset: int = 0,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    query = visible_query(user)
    if q:
        query = query.where(Ticket.title.ilike(f"%{q[:200]}%"))
    if kind:
        query = query.where(Ticket.kind == kind)
    if status:
        query = query.where(Ticket.status == status)
    if mine:
        query = query.where((Ticket.assignee_id if staff(user) else Ticket.creator_id) == user.id)
    if watching:
        query = query.where(
            Ticket.id.in_(select(Watcher.ticket_id).where(Watcher.user_id == user.id))
        )
    if severity:
        query = query.where(Ticket.severity == severity)
    if product_id:
        query = query.where(Ticket.product_id == product_id)
    if company_id:
        query = query.where(Ticket.company_id == company_id)
    if tag:
        if not staff(user):
            raise HTTPException(403, "Tags are internal to staff")
        query = query.where(
            Ticket.id.in_(select(TicketTag.ticket_id).where(TicketTag.name == tag.strip().lower()))
        )
    records = db.scalars(
        query.order_by(Ticket.updated_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 200)))
    ).all()
    return [ticket_dict(db, t, user) for t in records]


@app.post("/api/tickets", status_code=201)
def create_ticket(
    data: s.TicketCreate, user: User = Depends(identity), db: Session = Depends(get_db)
):
    values = data.model_dump()
    if not staff(user):
        if (
            data.kind != "support"
            or data.reproduction
            or data.affected_version
        ):
            raise HTTPException(403, "Internal fields require staff access")
        values["company_id"] = user.company_id
    exists(db, Product, data.product_id, "product")
    exists(db, Company, values["company_id"], "company")
    if data.kind == "support" and not values["company_id"]:
        raise HTTPException(422, "Support tickets require a client company")
    issue_type = db.get(IssueType, data.issue_type_id) if data.issue_type_id else None
    if not issue_type:
        issue_type = db.scalar(select(IssueType).where(
            IssueType.active.is_(True), IssueType.classification == data.incident_type
        ).order_by(IssueType.id))
    if not issue_type and data.issue_type_id is None:
        issue_type = IssueType(name=data.incident_type.replace("_", " ").title(), classification=data.incident_type, active=True)
        db.add(issue_type)
        db.flush()
    if not issue_type or not issue_type.active:
        raise HTTPException(422, "Choose an active issue type")
    category = db.get(IssueCategory, data.category_id) if data.category_id else None
    if not category:
        category = db.scalar(
            select(IssueCategory)
            .where(IssueCategory.active.is_(True), IssueCategory.product_id == data.product_id,
                   IssueCategory.parent_id.is_(None), IssueCategory.kind.in_([data.kind, "both"]))
            .order_by(IssueCategory.id)
        )
    if (not category or category.kind not in {data.kind, "both"} or not category.active
            or category.product_id != data.product_id or category.parent_id is not None):
        raise HTTPException(422, "Choose an active issue category")
    subcategory = db.get(IssueCategory, data.subcategory_id) if data.subcategory_id else None
    if data.subcategory_id and (not subcategory or not subcategory.active
            or subcategory.parent_id != category.id or subcategory.product_id != data.product_id
            or subcategory.kind not in {data.kind, "both"}):
        raise HTTPException(422, "Choose a subcategory within the selected category")
    values["category_id"] = category.id
    values["subcategory_id"] = subcategory.id if subcategory else None
    values["issue_type_id"] = issue_type.id
    values["incident_type"] = issue_type.classification
    if data.kind == "bug":
        values["company_id"] = None
    ticket = Ticket(**values, creator_id=user.id)
    policy = (
        db.scalar(select(Policy).where(Policy.company_id == values["company_id"]))
        if data.kind == "support"
        else None
    )
    ticket.sla_config = policy.config if policy else None
    db.add(ticket)
    db.flush()
    ticket.assignee_id = assign_ticket(db, ticket)
    sla.start_cycle(db, ticket, "resolution", ticket.created_at, always=True)
    if ticket.kind == "support":
        sla.start_cycle(db, ticket, "first_response", ticket.created_at, always=True)
        sla.start_cycle(db, ticket, "update", ticket.created_at)
    audit(db, user, "ticket_created", ticket)
    if not user.automation:
        db.add(Watcher(ticket_id=ticket.id, user_id=user.id))
    workspace.notify(
        db,
        ticket,
        user,
        "assigned" if ticket.assignee_id else "ticket_created",
        internal=ticket.kind == "bug",
    )
    workspace.confirm_creation(db, ticket, user)
    if ticket.assignee_id is None:
        workspace.notify_unassigned_staff_by_email(db, ticket, user)
    db.commit()
    return ticket_dict(db, ticket, user, True)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int, user: User = Depends(identity), db: Session = Depends(get_db)):
    return ticket_dict(db, ticket_access(db, user, ticket_id), user, True)


def transition(db, ticket, user, status, at):
    old = ticket.status
    if old == status:
        return
    ticket.status = status
    audit(db, user, "status_changed", ticket, {"from": old, "to": status}, at)
    workspace.notify(
        db, ticket, user, "approval_requested" if status == "pending_approval" else "status_changed"
    )
    for cycle in sla.cycles(db, ticket):
        if status in {"pending_approval", "closed"} and not cycle.completed_at:
            if cycle.metric in {"resolution", "update", "reply"}:
                cycle.completed_at = at
                cycle.actor_id = user.id
            # First response remains unsatisfied unless a human public message exists.
        elif (
            old in {"pending_approval", "closed"}
            and status not in {"pending_approval", "closed"}
            and cycle.metric == "resolution"
        ):
            cycle.completed_at, cycle.actor_id = None, None
    if old in {"pending_approval", "closed"} and status not in {
        "pending_approval",
        "closed",
    }:
        sla.start_cycle(db, ticket, "update", at)


def public_staff_reply(db, ticket, user, at, schedule_next=True):
    if user.automation:
        return
    for cycle in sla.cycles(db, ticket):
        if not cycle.completed_at and cycle.metric in {
            "first_response",
            "reply",
            "update",
        }:
            cycle.completed_at, cycle.actor_id = at, user.id
    if schedule_next and ticket.status not in {"pending_approval", "closed"}:
        sla.start_cycle(db, ticket, "update", at)


def apply_ticket_update(
    ticket_id: int,
    data: s.TicketUpdate,
    user: User,
    db: Session,
):
    ticket = ticket_access(db, user, ticket_id)
    if ticket.version != data.version:
        raise HTTPException(409, "This ticket changed. Refresh it and try again.")
    fields = data.model_fields_set - {"version", "reason"}
    if not staff(user):
        if (
            fields != {"status"}
            or ticket.status != "pending_approval"
            or data.status not in {"closed", "in_progress"}
        ):
            raise HTTPException(403, "Customers can approve or reject a proposed resolution")
        if data.status == "in_progress" and not data.reason.strip():
            raise HTTPException(422, "Explain why the resolution is rejected")
    if "assignee_id" in fields:
        if not (admin(user) or "assigner" in user.roles):
            raise HTTPException(403, "Ticket assigner permission required")
        validate_assignee(db, data.assignee_id)
    if "category_id" in fields:
        category = db.get(IssueCategory, data.category_id)
        if (not category or not category.active or category.kind not in {ticket.kind, "both"}
                or category.product_id != ticket.product_id or category.parent_id is not None):
            raise HTTPException(422, "Choose an active issue category")
        if "subcategory_id" not in fields:
            data.subcategory_id = None
            fields.add("subcategory_id")
    if "subcategory_id" in fields and data.subcategory_id is not None:
        category_id = data.category_id if "category_id" in fields else ticket.category_id
        subcategory = db.get(IssueCategory, data.subcategory_id)
        if (not subcategory or not subcategory.active or subcategory.parent_id != category_id
                or subcategory.product_id != ticket.product_id
                or subcategory.kind not in {ticket.kind, "both"}):
            raise HTTPException(422, "Choose a subcategory within the selected category")
    if "issue_type_id" in fields:
        issue_type = db.get(IssueType, data.issue_type_id)
        if not issue_type or not issue_type.active:
            raise HTTPException(422, "Choose an active issue type")
        data.incident_type = issue_type.classification
        fields.add("incident_type")
    if "linked_bug_id" in fields and data.linked_bug_id is not None:
        bug = db.get(Ticket, data.linked_bug_id)
        if not bug or bug.kind != "bug" or ticket.kind != "support":
            raise HTTPException(422, "Support tickets can link to an internal bug")
    if data.status == "pending_approval" and ticket.kind == "bug":
        raise HTTPException(422, "Internal bugs close without customer approval")
    if (
        staff(user)
        and ticket.kind == "support"
        and data.status == "closed"
        and ticket.status != "pending_approval"
    ):
        raise HTTPException(422, "Propose a resolution before closing a support ticket")
    at = now()
    ticket.updated_at = at
    resolving = data.status in {"pending_approval", "closed"} and ticket.status not in {
        "pending_approval",
        "closed",
    }
    if resolving and not (data.resolution or ticket.resolution).strip():
        raise HTTPException(422, "Provide a resolution before resolving the ticket")
    if resolving and user.automation and ticket.kind == "support":
        raise HTTPException(403, "A human must propose the customer resolution")
    changed_other = False
    for field in fields - {"status"}:
        value = getattr(data, field)
        if value is None and field not in {"assignee_id", "linked_bug_id", "subcategory_id"}:
            raise HTTPException(422, f"{field} cannot be null")
        previous = getattr(ticket, field)
        setattr(ticket, field, value)
        if previous != value:
            audit(
                db,
                user,
                "field_changed",
                ticket,
                {"field": field, "from": previous, "to": value},
                at,
            )
            if field == "assignee_id":
                workspace.notify(db, ticket, user, "assigned", internal=True)
            else:
                changed_other = True
    if changed_other:
        workspace.notify(db, ticket, user, "ticket_updated", internal=ticket.kind == "bug")
    # In-flight SLA targets remain fixed; classification changes cannot erase a breach.
    if resolving and ticket.kind == "support":
        db.add(
            Message(
                ticket_id=ticket.id,
                author_id=user.id,
                body="Resolution proposed:\n" + ticket.resolution,
                created_at=at,
            )
        )
        public_staff_reply(db, ticket, user, at, schedule_next=False)
    if data.status:
        transition(db, ticket, user, data.status, at)
    if data.reason.strip():
        db.add(Message(ticket_id=ticket.id, author_id=user.id, body=data.reason, created_at=at))
        if not staff(user) and ticket.status == "in_progress":
            sla.start_cycle(db, ticket, "reply", at)
    db.flush()
    return ticket


@app.patch("/api/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int,
    data: s.TicketUpdate,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    ticket = apply_ticket_update(ticket_id, data, user, db)
    db.commit()
    return ticket_dict(db, ticket, user, True)


@app.post("/api/tickets/{ticket_id}/messages", status_code=201)
def add_message(
    ticket_id: int,
    data: s.MessageInput,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    ticket = ticket_access(db, user, ticket_id)
    if data.internal and not staff(user):
        raise HTTPException(403, "Private notes require staff access")
    if not data.body.strip():
        raise HTTPException(422, "Message cannot be empty")
    if ticket.status == "closed":
        raise HTTPException(422, "Reopen the ticket before adding a reply")
    at = now()
    db.add(Message(ticket_id=ticket.id, author_id=user.id, **data.model_dump(), created_at=at))
    if not data.internal:
        if staff(user):
            public_staff_reply(db, ticket, user, at)
        else:
            if ticket.status == "waiting_customer":
                transition(db, ticket, user, "in_progress", at)
            if ticket.status != "pending_approval" and not any(
                c.metric == "reply" and not c.completed_at for c in sla.cycles(db, ticket)
            ):
                sla.start_cycle(db, ticket, "reply", at)
    ticket.updated_at = at
    audit(
        db,
        user,
        "private_note_added" if data.internal else "reply_added",
        ticket,
        at=at,
    )
    workspace.notify(
        db,
        ticket,
        user,
        "private_note" if data.internal else "staff_reply" if staff(user) else "customer_reply",
        internal=data.internal,
    )
    db.commit()
    return ticket_dict(db, ticket, user, True)


UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))


@app.post("/api/tickets/{ticket_id}/attachments", status_code=201)
def upload(
    ticket_id: int,
    internal: bool = False,
    file: UploadFile = File(...),
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    ticket = ticket_access(db, user, ticket_id)
    if internal and not staff(user):
        raise HTTPException(403, "Private attachments require staff access")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(24)
    path = UPLOAD_DIR / key
    size = 0
    try:
        with path.open("xb") as handle:
            while chunk := file.file.read(65536):
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise HTTPException(413, "Attachments must be 10 MB or smaller")
                handle.write(chunk)
        filename = (file.filename or "attachment").replace("\\", "/").split("/")[-1]
        filename = "".join(c for c in filename if c.isprintable())[:255] or "attachment"
        record = Attachment(
            ticket_id=ticket.id,
            author_id=user.id,
            filename=filename,
            storage_key=key,
            size=size,
            internal=internal,
        )
        db.add(record)
        ticket.updated_at = now()
        audit(
            db,
            user,
            "attachment_added",
            ticket,
            {"filename": filename, "internal": internal},
        )
        workspace.notify(db, ticket, user, "attachment_added", internal=internal)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"id": record.id, "filename": filename, "size": size}


@app.get("/api/attachments/{attachment_id}")
def download(attachment_id: int, user: User = Depends(identity), db: Session = Depends(get_db)):
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise HTTPException(404, "Attachment not found")
    ticket_access(db, user, attachment.ticket_id)
    if attachment.internal and not staff(user):
        raise HTTPException(404, "Attachment not found")
    path = UPLOAD_DIR / attachment.storage_key
    if not path.is_file():
        raise HTTPException(404, "Attachment file unavailable")
    return FileResponse(path, media_type="application/octet-stream", filename=attachment.filename)


@app.get("/api/reports")
def reports(user: User = Depends(identity), db: Session = Depends(get_db)):
    return [
        {
            "id": r.id,
            "name": r.name,
            "owner_id": r.owner_id,
            "shared": r.shared,
            "config": r.config,
        }
        for r in db.scalars(
            select(Report).where((Report.owner_id == user.id) | Report.shared.is_(True))
        )
    ]


@app.post("/api/reports", status_code=201)
def save_report(data: s.ReportInput, user: User = Depends(identity), db: Session = Depends(get_db)):
    require_reports(user)
    report = Report(
        owner_id=user.id,
        name=data.name,
        shared=data.shared,
        config=data.config.model_dump(mode="json"),
    )
    db.add(report)
    audit(db, user, "report_created", details={"name": data.name, "shared": data.shared})
    db.commit()
    return {"id": report.id, "name": report.name}


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: int, user: User = Depends(identity), db: Session = Depends(get_db)):
    require_reports(user)
    report = db.get(Report, report_id)
    if not report or (report.owner_id != user.id and not admin(user)):
        raise HTTPException(404, "Report not found")
    db.delete(report)
    db.commit()
    return {"ok": True}


def run_report(db, user, config):
    query = visible_query(user)
    for field in [
        "status",
        "severity",
        "company_id",
        "product_id",
        "assignee_id",
        "kind",
        "incident_type",
    ]:
        value = getattr(config, field)
        if value is not None:
            query = query.where(getattr(Ticket, field) == value)
    if config.from_date:
        query = query.where(
            Ticket.created_at >= datetime.combine(config.from_date, datetime.min.time())
        )
    if config.to_date:
        query = query.where(
            Ticket.created_at
            < datetime.combine(config.to_date, datetime.min.time()) + timedelta(days=1)
        )
    grouped = defaultdict(
        lambda: {
            "tickets": 0,
            "values": [],
            "targeted": 0,
            "met": 0,
            "breached": 0,
            "open": 0,
        }
    )
    records = db.scalars(query).all()
    if config.view == "records":
        rows = []
        columns = list(dict.fromkeys(config.columns))
        for ticket in records:
            row = {}
            for field in columns:
                if field in {"company", "product", "assignee", "creator"}:
                    model = {
                        "company": Company,
                        "product": Product,
                        "assignee": User,
                        "creator": User,
                    }[field]
                    record_id = getattr(ticket, field + "_id")
                    row[field] = (
                        db.get(model, record_id).name
                        if record_id
                        else "Unassigned"
                        if model == User
                        else "Internal"
                    )
                elif field.endswith("_minutes"):
                    cycle = next(
                        (
                            c
                            for c in sla.cycles(db, ticket)
                            if c.metric == field.removesuffix("_minutes") and c.completed_at
                        ),
                        None,
                    )
                    row[field] = round(sla.elapsed(db, ticket, cycle), 2) if cycle else None
                else:
                    value = getattr(ticket, field)
                    row[field] = value.isoformat() + "Z" if isinstance(value, datetime) else value
            rows.append(row)
        return {
            "view": "records",
            "columns": columns,
            "rows": rows,
            "total_tickets": len(records),
            "metric": config.metric,
            "group_by": config.group_by,
            "note": "Records are restricted to the viewer's ticket permissions. Duration fields use completed SLA cycles in working minutes; empty values indicate incomplete cycles.",
        }
    for ticket in records:
        key = getattr(ticket, config.group_by, None)
        if config.group_by in {"assignee", "company", "product"}:
            model = {"assignee": User, "company": Company, "product": Product}[config.group_by]
            record_id = getattr(ticket, config.group_by + "_id")
            key = (
                db.get(model, record_id).name
                if record_id
                else "Unassigned"
                if model == User
                else "Internal"
            )
        ticket_cycles = sla.cycles(db, ticket)
        if config.group_by == "first_response_agent":
            first = next(
                (c for c in ticket_cycles if c.metric == "first_response" and c.actor_id),
                None,
            )
            key = db.get(User, first.actor_id).name if first else "Awaiting response"
        bucket = grouped[str(key)]
        bucket["tickets"] += 1
        if config.metric != "count":
            for cycle in ticket_cycles:
                if cycle.metric != config.metric or cycle.cancelled:
                    continue
                used = sla.elapsed(db, ticket, cycle)
                if cycle.completed_at:
                    bucket["values"].append(used)
                else:
                    bucket["open"] += 1
                if cycle.target_minutes and (cycle.completed_at or used > cycle.target_minutes):
                    bucket["targeted"] += 1
                    bucket["breached"] += int(used > cycle.target_minutes)
                    bucket["met"] += int(used <= cycle.target_minutes)
    rows = []
    for group, bucket in sorted(grouped.items()):
        values = sorted(bucket.pop("values"))

        def percentile(p):
            if not values:
                return None
            pos = (len(values) - 1) * p
            lo, hi = math.floor(pos), math.ceil(pos)
            return round(values[lo] + (values[hi] - values[lo]) * (pos - lo), 2)

        rows.append(
            {
                "group": group,
                **bucket,
                "completed": len(values),
                "average_minutes": round(sum(values) / len(values), 2) if values else None,
                "median_minutes": percentile(0.5),
                "p90_minutes": percentile(0.9),
                "compliance_percent": round(bucket["met"] / bucket["targeted"] * 100, 1)
                if bucket["targeted"]
                else None,
            }
        )
    return {
        "view": "summary",
        "rows": rows,
        "total_tickets": len(records),
        "metric": config.metric,
        "group_by": config.group_by,
        "note": "Duration statistics use completed cycles. Compliance includes completed targets and open breaches. Times follow each ticket's snapshotted SLA calendar; tickets without SLAs use wall-clock time. Agent grouping uses current assignee; first response agent uses the actual responding human.",
    }


@app.post("/api/reports/run")
def custom_report(
    data: s.ReportConfig, user: User = Depends(identity), db: Session = Depends(get_db)
):
    require_reports(user)
    return run_report(db, user, data)


@app.get("/api/reports/overview")
def overview(user: User = Depends(identity), db: Session = Depends(get_db)):
    return run_report(db, user, s.ReportConfig(group_by="status"))


@app.get("/api/reports/{report_id}/run")
def saved_report(
    report_id: int,
    export: bool = False,
    user: User = Depends(identity),
    db: Session = Depends(get_db),
):
    report = db.get(Report, report_id)
    if not report or (report.owner_id != user.id and not report.shared):
        raise HTTPException(404, "Report not found")
    result = run_report(db, user, s.ReportConfig(**report.config))
    if export:
        buffer = io.StringIO()
        fields = result.get("columns") or [
            "group",
            "tickets",
            "completed",
            "open",
            "average_minutes",
            "median_minutes",
            "p90_minutes",
            "met",
            "breached",
            "compliance_percent",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in result["rows"]:
            writer.writerow(
                {
                    k: (
                        "'" + v
                        if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                        else v
                    )
                    for k, v in row.items()
                }
            )
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="report.csv"'},
        )
    return result
