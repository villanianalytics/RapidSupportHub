# Ubuntu deployment

The reference deployment uses a single Ubuntu 24.04 machine, PostgreSQL 16, one Uvicorn process, nginx, and Let's Encrypt. PostgreSQL uses local Unix socket peer authentication: the `rapidsupporthub` operating-system user connects as the database role of the same name. No database password is needed in this topology.

## Install

1. Point your DNS A record at the server, and permit TCP 80 and 443 in the provider firewall. Keep SSH restricted appropriately.
2. Install `python3-venv postgresql nginx certbot python3-certbot-nginx` using apt.
3. Build the frontend (`pnpm install --frozen-lockfile && pnpm build`). Run `python scripts/package-release.py`, then copy `.local/release.tar.gz` to the server and extract it into `/opt/rapidsupporthub`.
4. Adapt `deploy/nginx.conf` to your domain.
5. Create `/etc/rapidsupporthub.env` with mode `600`, owned by root:

```dotenv
ADMIN_PASSWORD=YOUR_UNIQUE_TEMPORARY_PASSWORD
ADMIN_EMAIL=YOUR_ADMIN_EMAIL
DATABASE_URL=postgresql+psycopg:///rapidsupporthub
UPLOAD_DIR=/var/lib/rapidsupporthub/uploads
APP_ORIGIN=https://YOUR_DOMAIN
COOKIE_SECURE=true
```

6. Run `sudo bash /opt/rapidsupporthub/deploy/setup.sh`. This creates the service user, database, directories, and systemd units.
7. Run `sudo certbot --nginx -d YOUR_DOMAIN --redirect` and follow the certificate registration prompts.
8. Verify `/api/health`, sign in, and change the administrator password. Remove `ADMIN_PASSWORD` from the environment file after successful seeding. Clear any temporary credential transfer files.

The API binds only to `127.0.0.1:8000`; nginx terminates HTTPS. Secure cookies mean you must use HTTPS for production sign-in. Keep one Uvicorn worker for the in-process login limiter; nginx also applies an IP-based login rate limit.

## Operations

```sh
sudo systemctl status rapidsupporthub
sudo journalctl -u rapidsupporthub --since '1 hour ago'
sudo nginx -t
sudo systemctl list-timers rapidsupporthub-backup.timer certbot.timer
curl -fsS https://YOUR_DOMAIN/api/health
```

Code lives in `/opt/rapidsupporthub`, uploads in `/var/lib/rapidsupporthub/uploads`, and configuration in `/etc/rapidsupporthub.env`. The service is unprivileged, with a read-only system view and write access limited to application data and private temporary files.

For updates, back up first, deploy the new backend and frontend build, and restart `rapidsupporthub`. **Do not rerun the initial nginx setup over the Certbot-managed configuration**; preserve its TLS sections and apply only intentional changes. Preserve a previous release for rollback. Database schema changes need migrations before deploying a new model definition.

## Backups

### v0.1 to v0.2

This upgrade creates `ticket_watchers`, `notifications`, `ticket_tags`, `ticket_duplicates`, and `saved_views`. Existing tables and data remain intact. Take a backup and preserve the previous application release, install the new backend and frontend, then restart the service. Startup creates the five tables. Rolling the application back to v0.1 can leave these unused tables in place. Do not drop them if they contain new activity you want to preserve.

New activity generates notifications after deployment. Existing creators and assignees receive future updates without needing a watcher backfill. No historical inbox events are synthesized.

### v0.2 to v0.3

Install the updated Python requirements (adds PyJWT with cryptography), configure a private `SSO_ENCRYPTION_KEY`, and back up the database and environment file before updating. Startup adds `entra_connections`, `entra_identities`, and `entra_flows`; existing tables and accounts are unchanged. SSO remains unavailable until an administrator registers a connection and enables it. See [SSO setup](SSO.md). Preserve the encryption key alongside database backups, and keep the previous application release for rollback.

The systemd timer runs at **07:00 UTC daily**, with 14-day retention. It briefly stops the application, takes a PostgreSQL custom-format dump and an upload archive, then restarts it. This keeps files and database references consistent. Expect a short maintenance interruption during backups.

Run a backup manually:

```sh
sudo systemctl start rapidsupporthub-backup.service
sudo journalctl -u rapidsupporthub-backup.service -n 20
sudo ls -lh /var/backups/rapidsupporthub
```

Archives and checksums are root-readable only. They include configuration and customer data. **Same-server backups do not protect against server loss.** Arrange encrypted off-server replication separately.

To verify an archive, run `sha256sum -c ARCHIVE.sha256`, extract it into a protected temporary directory, and run `pg_restore --list database.dump` and `tar -tzf uploads.tar.gz`. Periodically restore into a separate scratch database and verify records.

## Restore

During an intentional recovery window:

1. Stop `rapidsupporthub` and preserve the current database/uploads before changing them.
2. Validate and extract the selected archive into a root-only directory.
3. Restore `database.dump` with `pg_restore --clean --if-exists --no-owner --role=rapidsupporthub` into the intended database as the PostgreSQL administrator.
4. Restore the upload archive under `/var/lib/rapidsupporthub`, ensuring ownership is `rapidsupporthub:rapidsupporthub` and permissions remain private.
5. Restore or reconcile the environment file, then start the service and verify health, sign-in, ticket counts, permissions, and attachment downloads.

Never test a restore over the live database.
