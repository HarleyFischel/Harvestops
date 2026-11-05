#!/usr/bin/env bash
set -euo pipefail
export APP_ENV="${APP_ENV:-development}"
export DEMO_MODE="${DEMO_MODE:-true}"
export STORAGE_MODE="${STORAGE_MODE:-demo}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
"$PYTHON_BIN" -m harvestops.web
