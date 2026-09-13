# RapidSupportHub

A lightweight, self-hosted support portal and internal issue tracker, built with **FastAPI, React, TypeScript, and PostgreSQL**. Apache-2.0 licensed.

## Initial release

- Customer portal with own-ticket and company-wide access roles that combine additively.
- Staff ticket queue and Kanban board, with assignment, severity, incident type, and product/project organization.
- Internal bugs, reproduction steps, affected versions, resolutions, private notes, and private attachments.
- Customer tickets linked to internal bugs without exposing internal records to clients.
- Proposed resolutions, customer approval/rejection, reopening, and an audit trail.
- Client SLA calendars and targets for first human response, resolution, optional customer reply time, and optional progress updates.
- Configurable summary and record reports, filters, selectable columns, saved/shared reports, and CSV exports. Every run enforces the viewer's current record permissions.
- Dedicated automation accounts with expiring, scoped, revocable REST API keys.
- Responsive interface, secure session cookies, Argon2 password hashing, first-login password changes, and upload authorization.

Email ingestion, email delivery, and notifications are intentionally **not enabled in v0.1**. Conversations happen through the portal.

## Local development

Requirements: Python 3.11+, Node.js 22.12+ (24 LTS works), and pnpm. SQLite is the default for local use; PostgreSQL is used in production.

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead: .venv/Scripts/Activate.ps1
python -m pip install -r backend/requirements.txt
cp .env.example .env
```

Set a unique `ADMIN_PASSWORD` of at least 12 characters in `.env`. The first startup creates `SupportAdmin`; there is **no built-in default password**. Replace the temporary password on first login. Remove the bootstrap password from the environment after the account exists.

```sh
cd backend
python -m uvicorn app.main:app --reload --env-file ../.env --host 127.0.0.1 --port 8000
```

In a separate terminal:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Open http://localhost:5173. The Vite proxy forwards `/api` to FastAPI. Keep `APP_ORIGIN` aligned with the browser URL. API documentation is available at `/api/docs`, with the OpenAPI schema at `/api/openapi.json`.

## Set up your workspace

1. Sign in as `SupportAdmin` and change the temporary password.
2. Under **Settings → Workspace**, add products/projects and client companies.
3. Under **People & permissions**, create staff and customer users. Customers must belong to a company; deliver temporary credentials through your normal secure channel.
4. Give customers **Own tickets**, **Company tickets**, or both. Staff roles see all support records and internal issues in this single-team installation.
5. Optionally configure each client's SLA policy before creating their tickets.
6. Grant **Manage custom reports** to users who should create and share reports. Others may run shared reports against their own authorized data.
7. For integrations, create an automation user and issue a key under **API access**.

## REST API

All application actions use `/api`. Interactive sign-in uses an HttpOnly, SameSite session cookie. Cookie-authenticated writes require an allowed `Origin` and `X-Requested-With: RapidSupportHub` header.

Automation clients use a dedicated user and a bearer key:

```sh
curl https://your-domain.example/api/tickets \
  -H "Authorization: Bearer $RSH_API_KEY"
```

Scopes are `read`, `write`, and `reports`; they grant endpoint access, while the automation user's roles restrict its data. Keys cannot access administrator or authentication mutation endpoints. API responses include a ticket `version`; PATCH requests must send that version and receive HTTP 409 if it is stale.

Example ticket creation payload:

```json
{
  "title": "CSV export times out",
  "description": "Exports fail for datasets above 100,000 rows.",
  "kind": "support",
  "company_id": 1,
  "product_id": 1,
  "severity": "sev2",
  "incident_type": "bug"
}
```

## Workflow and SLA semantics

The normal flow is **New → Started → In progress → Pending approval → Closed**. Waiting on customer is available separately. Staff enter a resolution before proposing it; this creates a public human reply. Customers can approve and close it, or reject it with an explanation. Internal bugs close directly with a resolution.

- First response begins at creation and is completed only by a human public staff reply. Private notes, uploads, and automation replies do not satisfy it.
- Resolution begins at creation. It stops at a proposed resolution and resumes if the ticket reopens. Approval/closed periods are excluded from resumed resolution time. The audit log preserves every proposal, rejection, and closure.
- Optional reply timing begins with the first unanswered customer message. Additional customer messages do not reset its start.
- Optional update timing begins at creation, then restarts after each human public reply while active.
- SLA calendars support 24/7 coverage or a daily business window, selected weekdays, IANA timezone, and explicit holidays. Business windows handle daylight-saving changes.
- Waiting-on-customer pauses all configured clocks when enabled. A new customer reply moves a waiting ticket to In progress. Approval/closed periods pause outstanding clocks.
- Policies are snapshotted at ticket creation. Active cycles retain their original targets even if classification changes. Future reply/update cycles select targets using the ticket's current classification from its original policy snapshot.
- First response and resolution are measured even without a policy; internal bugs have resolution measurements. No-policy duration uses wall-clock time. Business SLA duration uses working minutes.
- Reports use completed cycles for average, median, and P90. Compliance includes completed targets and open breaches; unbreached open targets remain pending. Repeated reply/update cycles are separate observations.
- Assignee grouping uses the current assignee. **First response agent** uses the human who actually responded. Assignment history remains in the audit trail.

## Verification

```sh
cd backend
python -m pytest -q
cd ../frontend
pnpm build
```

For the browser workflow test, start the isolated API with `python scripts/run-e2e-api.py` from the repository root and Vite with `pnpm dev --host 127.0.0.1`, then run:

```sh
cd frontend
pnpm exec playwright install chromium
pnpm exec playwright test
```

The test uses a disposable SQLite database and test-only credentials. Restart the isolated API before each full browser test run. It never targets the production database.

## Deployment and operations

See [deployment instructions](docs/DEPLOYMENT.md) for Ubuntu, PostgreSQL, systemd, nginx, TLS, backups, and restore checks.

## Deliberate v0.1 boundaries

- Single support organization. Staff roles have workspace-wide access; per-project staff restrictions are not implemented.
- Accounts are administrator-created. Self-registration, self-service password recovery, SSO, and MFA are not implemented.
- Reports cover ticket records and the four SLA measurements, not arbitrary SQL, custom database joins, or a general-purpose BI engine. SLA alerts are visual; automated escalation and notification delivery are future work.
- Reports run synchronously; this release is intended for a small support team. Large installations will need query optimization and background exports.
- Schema creation is for initial installation. Add versioned migrations before changing a deployed schema; `create_all` does not upgrade existing tables.
- Attachments are authorized downloads with a 10 MB limit, not inline previews. Malware scanning and per-client storage quotas are not included.
- Backups are stored on the same server by default. Configure off-server replication to protect against server loss.
