#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${PYTHON_BIN:-}" ]]; then
  for candidate in .venv312/bin/python .venv/bin/python; do
    if [[ -x "$candidate" ]]; then PYTHON_BIN="$candidate"; break; fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
"$PYTHON_BIN" -m pytest
