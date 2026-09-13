#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'Run with sudo'; exit 1; fi
test -s /etc/rapidsupporthub.env || { echo 'Install /etc/rapidsupporthub.env first'; exit 1; }
id rapidsupporthub >/dev/null 2>&1 || useradd --system --home /var/lib/rapidsupporthub --shell /usr/sbin/nologin rapidsupporthub
install -d -o rapidsupporthub -g rapidsupporthub -m 700 /var/lib/rapidsupporthub /var/lib/rapidsupporthub/uploads
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='rapidsupporthub'" | grep -q 1; then
    runuser -u postgres -- createuser rapidsupporthub
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='rapidsupporthub'" | grep -q 1; then
    runuser -u postgres -- createdb -O rapidsupporthub rapidsupporthub
fi
python3 -m venv /opt/rapidsupporthub/venv
/opt/rapidsupporthub/venv/bin/pip install --disable-pip-version-check -r /opt/rapidsupporthub/backend/requirements.txt
chmod 600 /etc/rapidsupporthub.env
chmod +x /opt/rapidsupporthub/deploy/backup.sh
cp /opt/rapidsupporthub/deploy/rapidsupporthub*.service /etc/systemd/system/
cp /opt/rapidsupporthub/deploy/rapidsupporthub-backup.timer /etc/systemd/system/
cp /opt/rapidsupporthub/deploy/nginx.conf /etc/nginx/sites-available/rapidsupporthub
ln -sfn /etc/nginx/sites-available/rapidsupporthub /etc/nginx/sites-enabled/rapidsupporthub
nginx -t
systemctl daemon-reload
systemctl enable --now rapidsupporthub rapidsupporthub-backup.timer
systemctl reload nginx
