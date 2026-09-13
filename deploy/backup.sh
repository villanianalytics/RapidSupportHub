#!/usr/bin/env bash
set -euo pipefail
umask 077
backup_root=/var/backups/rapidsupporthub
mkdir -p "$backup_root"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d "$backup_root/.backup-XXXXXX")
trap 'rm -rf -- "$work"' EXIT
# Briefly stop writes so database and attachment contents form one consistent snapshot.
systemctl stop rapidsupporthub
trap 'systemctl start rapidsupporthub; rm -rf -- "$work"' EXIT
runuser -u postgres -- pg_dump -Fc rapidsupporthub > "$work/database.dump"
tar -czf "$work/uploads.tar.gz" -C /var/lib/rapidsupporthub uploads
cp /etc/rapidsupporthub.env "$work/environment"
systemctl start rapidsupporthub
tar -czf "$backup_root/$stamp.tar.gz" -C "$work" .
sha256sum "$backup_root/$stamp.tar.gz" > "$backup_root/$stamp.tar.gz.sha256"
find "$backup_root" -maxdepth 1 -type f -name '*.tar.gz*' -mtime +14 -delete
echo "Backup completed: $stamp"
