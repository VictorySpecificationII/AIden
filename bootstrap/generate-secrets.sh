#!/bin/bash
# Create the service passwords in secrets/ (gitignored): one random value per file.
#
# Existing files are never overwritten, so it is safe to run again; nothing is printed.
# The folder is mode 700, so only you can reach the files on the host. The files
# themselves are readable (644) because Docker Compose mounts them into containers
# that run as other users (Grafana as 472, ...) and ignores per-secret modes.
#
# Rotate one: delete its file, run this again, then follow docs in docker-compose.yaml.
# Back them up somewhere safe (e.g. Bitwarden) when online: a lost laptop otherwise
# means resetting each service.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/secrets"
mkdir -p "$DIR"
chmod 700 "$DIR"
created=0
for name in grafana_admin_password postgres_password minio_root_password mlflow_s3_secret_key \
            elastic_password webui_secret_key; do
    file="$DIR/$name"
    if [ ! -s "$file" ]; then
        # 32 characters: within every service's limits (MinIO secret keys allow 8-40)
        python3 -c 'import secrets; print(secrets.token_urlsafe(24), end="")' > "$file"
        created=$((created + 1))
    fi
    chmod 644 "$file"
done
echo "secrets/: $created created, $(ls "$DIR" | wc -l) in total (values not shown)."
