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

In-app notifications are enabled. Email ingestion and delivery remain deferred; conversations happen through the portal.

## Daily operations (v0.2)

The portal adapts to phones and tablets: labeled mobile navigation, ticket and attention cards, expandable filters, larger touch controls, and stacked forms. Open a Kanban card to change status on touch devices. Wide administrative/report tables can be swiped horizontally. Browser coverage includes 320, 390, 768, and 1024-pixel viewports plus a touch-enabled customer workflow.

Microsoft Entra ID / Azure AD single sign-on is available in **Settings → Single sign-on** as of v0.3. See [SSO setup](docs/SSO.md) for app registration, explicit user mappings, and secret management. Local password login remains available.

- **My account** lets users change their password. Administrators can reset another human user's password or require a change under **Settings → People & permissions → Password options**. Both administrator actions revoke existing sessions and API credentials. Temporary passwords must be replaced at login.
- **Notifications** shows assignments, replies, private notes (staff only), and status/approval activity. Creators, current assignees, and ticket watchers receive relevant events, excluding their own actions. Notifications are rechecked against current permissions; watching never grants access. Staff can add colleagues as watchers from ticket details. Inboxes refresh every 30 seconds.
- **Attention needed** ranks active tickets with breached SLAs, approaching SLAs (80% elapsed), unanswered customer conversations, or no assignee. Pending-approval and closed tickets are excluded. Categories can overlap; filters and counts respect ticket access.
- Ticket lists support personal saved views, severity/product/client/tag filters, and a Watching filter. Saved views retain search, status, assignment, filters, and list/board layout.
- Staff can manage tags and same-kind duplicate links in ticket details. Links preserve both records and SLA history, and cannot form cycles. Tags and duplicate links are internal.
- Staff can select up to 100 visible tickets and change assignment or status together. Every ticket's version, permissions, and resolution rules must pass; otherwise the entire action rolls back.

These features are available through the REST API documented at `/api/docs`. No historical notifications are generated on upgrade.

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

## Deliberate boundaries

- Single support organization. Staff roles have workspace-wide access; per-project staff restrictions are not implemented.
- Accounts are administrator-created. Self-registration and self-service password recovery are not implemented. Entra SSO supports tenant-managed MFA; local-password MFA is not implemented.
- Reports cover ticket records and the four SLA measurements, not arbitrary SQL, custom database joins, or a general-purpose BI engine. SLA attention is visible in the queue; automated escalation and email delivery are future work.
- Reports run synchronously; this release is intended for a small support team. Large installations will need query optimization and background exports.
- v0.2 adds five tables without changing existing tables. Back up before deploying; startup creates the new tables. Future changes to existing columns require versioned migrations because `create_all` does not upgrade them.
- Attachments are authorized downloads with a 10 MB limit, not inline previews. Malware scanning and per-client storage quotas are not included.
- Backups are stored on the same server by default. Configure off-server replication to protect against server loss.

The built-in **Help center** provides searchable, role-relevant guides for customer tickets, internal bugs, Kanban, SLAs, reports, accounts, SSO, and API automation. The top-bar question mark opens contextual help without leaving the current work; Settings tabs also link to their setup guides. Guide content lives in `frontend/src/help-content.ts` and ships with the application.

## Audit center

Administrators can search and export application audit events under **Audit center**. API activity (reads, writes, authentication, denials, report runs and downloads) is correlated with transactional record history through request IDs. ORM inserts, edits, deletes, and bulk updates/revocations record sanitized before/after values in the same transaction as the affected records; rolled-back changes do not survive. Audit CSV exports require an interactive administrator session and are limited to 10,000 filtered events.

A new `audit_events` table is created on startup and existing business audit entries are imported once. Request starts are durable separately from outcomes so interruptions leave evidence. A successful HTTP response for a file means the response was initiated, not that delivery completed. Database triggers reject ordinary updates/deletes; database owners can still bypass them. There is no automatic pruning or portal deletion capability. Maintain secure database backups and monitor storage growth, including polling traffic. Logging failures fail the request; committed change records must be reviewed before retrying an interrupted mutation.

Passwords, hashes, tokens, SSO secrets and raw HTTP bodies/query strings are excluded. Message/description/reproduction/resolution changes retain character counts rather than text. Historical records cannot supply metadata that was not originally captured. Health checks, static assets, browser-only interactions, direct SQL changes and operating-system activity are outside this application-level audit trail. Trusted proxy settings must remain restricted to the local reverse proxy for meaningful client IP attribution.

## Amazon SES SMTP readiness

Administrators can store an Amazon SES SMTP connection under **Settings → Email delivery**. The application derives the regional `email-smtp.<region>.amazonaws.com` endpoint, supports STARTTLS on port 587 and TLS on port 465, encrypts the SMTP password at rest, and never returns it to the browser. Saving and testing the configuration produces redacted audit events.

The connection test authenticates without sending a message. This release does not send ticket email or ingest tickets from email; the configuration prepares those capabilities for the next phase. SES identities, sandbox/production access, suppression handling, delivery events, bounce/complaint processing, and notification rules must still be configured when outbound delivery is implemented.
