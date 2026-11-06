#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in .venv/bin/python .venv312/bin/python; do
    if [[ -x "$candidate" ]]; then PYTHON_BIN="$candidate"; break; fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
HARVESTOPS_URL="${HARVESTOPS_URL:-http://127.0.0.1:8050}" "$PYTHON_BIN" -m pytest tests/browser -q
