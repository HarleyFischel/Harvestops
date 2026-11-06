#!/usr/bin/env bash
set -euo pipefail

# This runs the ARM64 application image and connects to an external SQL Server.
# It never starts a local SQL Server container on the Mac.
compose_file="${COMPOSE_FILE:-compose.mac.yml}"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run ./scripts/init-env.sh, then configure SQL_SERVER/SQL_DATABASE/SQL_USER/SQL_PASSWORD." >&2
  exit 2
fi

docker compose -f "$compose_file" build app
docker compose -f "$compose_file" run --rm app python -c '
from harvestops.config import get_settings
from harvestops.repository import SqlServerRepository

settings = get_settings()
errors = settings.validate_for_runtime()
if settings.storage_mode != "sqlserver":
    errors.append("STORAGE_MODE must be sqlserver for external SQL verification")
if errors:
    raise SystemExit("Invalid external SQL configuration: " + "; ".join(errors))

repository = SqlServerRepository(settings)
repository.ping()
database = repository.query("SELECT DB_NAME() AS database_name")[0]["database_name"]
print({"server": settings.sql_server, "database": database, "auth_mode": settings.sql_auth_mode, "tls_verified": not settings.sql_trust_server_certificate})
'

if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  echo "Applying versioned migrations to the configured external database..."
  docker compose -f "$compose_file" run --rm app python db/run_migrations.py
fi

echo "External SQL preflight passed. No local SQL Server container was started."
