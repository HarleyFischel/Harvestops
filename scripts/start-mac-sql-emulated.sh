#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env.mac-sql}"
compose_file="compose.mac-sql-emulated.yml"
timeout_seconds="${STARTUP_TIMEOUT_SECONDS:-2700}"

if [[ ! -f "$env_file" ]]; then
  printf 'Missing %s. Run ./scripts/init-mac-sql-env.sh first.\n' "$env_file" >&2
  exit 2
fi

compose=(docker compose --env-file "$env_file" -f "$compose_file")
start_epoch="$(date +%s)"

health_status() {
  local service="$1"
  local id
  id="$("${compose[@]}" ps -aq "$service")"
  [[ -n "$id" ]] || return 1
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id"
}

dump_diagnostics() {
  "${compose[@]}" ps || true
  "${compose[@]}" logs --tail=200 sqlserver database-bootstrap migrations app || true
}

if ! "${compose[@]}" up --build -d; then
  printf 'Compose startup failed; diagnostics follow.\n' >&2
  dump_diagnostics
  exit 1
fi

while true; do
  now="$(date +%s)"
  if (( now - start_epoch >= timeout_seconds )); then
    printf 'Timed out after %s seconds. SQL emulation diagnostics follow.\n' "$timeout_seconds" >&2
    dump_diagnostics
    exit 1
  fi

  sql_status="$(health_status sqlserver 2>/dev/null || true)"
  app_status="$(health_status app 2>/dev/null || true)"
  bootstrap_status="$(health_status database-bootstrap 2>/dev/null || true)"
  migration_status="$(health_status migrations 2>/dev/null || true)"
  if [[ "$sql_status" == healthy && "$bootstrap_status" == exited && "$migration_status" == exited && "$app_status" == healthy ]]; then
    printf 'HarvestOps SQL-backed Mac stack is ready on http://127.0.0.1:%s.\n' "$(awk -F= '$1=="HARVESTOPS_MAC_SQL_APP_PORT" {print $2}' "$env_file")"
    exit 0
  fi
  if [[ "$sql_status" == unhealthy || "$bootstrap_status" == dead || "$migration_status" == dead || "$app_status" == unhealthy ]]; then
    printf 'A SQL stack service failed; diagnostics follow.\n' >&2
    dump_diagnostics
    exit 1
  fi
  sleep 5
done
