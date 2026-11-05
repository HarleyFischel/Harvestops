#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python || command -v python3)}"
"$PYTHON_BIN" -m pytest
"$PYTHON_BIN" -c 'from harvestops.config import Settings; from harvestops.services import InMemoryStore; s=Settings(); print({"app_env": s.app_env, "storage_mode": s.storage_mode, "identity_mode": s.identity_mode, "sql_server": s.sql_server, "sql_password_configured": bool(s.sql_password)}); print(InMemoryStore().kpis({}))'
printf 'Local demo verification passed. Docker, browser, SQL Server, and Azure checks are separate gates.\n'
