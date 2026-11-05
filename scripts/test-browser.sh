#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
HARVESTOPS_URL="${HARVESTOPS_URL:-http://127.0.0.1:8050}" "$PYTHON_BIN" -m pytest tests/browser -q
