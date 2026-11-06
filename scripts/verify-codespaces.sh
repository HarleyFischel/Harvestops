#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in .venv/bin/python .venv312/bin/python; do
    if [[ -x "$candidate" ]]; then PYTHON_BIN="$candidate"; break; fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
HARVESTOPS_URL="${HARVESTOPS_URL:-http://127.0.0.1:8050}"
RUN_BROWSER="${RUN_BROWSER:-false}"
started_pid=""
log_file="${TMPDIR:-/tmp}/harvestops-codespaces-verify.log"

cleanup() {
  if [[ -n "$started_pid" ]] && kill -0 "$started_pid" 2>/dev/null; then
    kill "$started_pid" 2>/dev/null || true
    wait "$started_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if ! curl --fail --silent "$HARVESTOPS_URL/healthz" >/dev/null 2>&1; then
  APP_ENV=development DEMO_MODE=true STORAGE_MODE=demo IDENTITY_MODE=demo \
    "$PYTHON_BIN" -m harvestops.web >"$log_file" 2>&1 &
  started_pid=$!
  ready=false
  for _ in $(seq 1 30); do
    if curl --fail --silent "$HARVESTOPS_URL/healthz" >/dev/null 2>&1; then
      ready=true
      break
    fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    cat "$log_file"
    printf '%s\n' 'HarvestOps did not become ready.' >&2
    exit 1
  fi
fi

PYTHON_BIN="$PYTHON_BIN" ./scripts/verify-local.sh
if [[ "$RUN_BROWSER" == true ]]; then
  HARVESTOPS_URL="$HARVESTOPS_URL" PYTHON_BIN="$PYTHON_BIN" ./scripts/test-browser.sh
fi
printf 'Codespaces verification passed. Browser checks: %s.\n' "$RUN_BROWSER"
