#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
"$PYTHON_BIN" -m pytest
"$PYTHON_BIN" -c 'from harvestops.config import Settings; from harvestops.services import InMemoryStore; print(Settings().model_dump()); print(InMemoryStore().kpis({}))'
printf 'Local demo verification passed. Docker, browser, SQL Server, and Azure checks are separate gates.\n'
