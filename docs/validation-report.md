# Validation report

Date: 2026-11-05. Host: Apple Silicon M2, 8 GiB RAM, macOS, Python 3.12 virtual environment. Disk: 170 GiB free at start. Docker CLI 29.8.0 is installed; Docker daemon was not reachable at start.

## Completed evidence

- Repository connected to https://github.com/HarleyFischel/Harvestops.git; initial commit was 85be7ca.
- pip install -e '.[dev]' completed in .venv312 using Python 3.12.
- .venv312/bin/python -m pytest -q passed: 9 tests.
- ruff check . passed.
- Flask test-client smoke checks returned /healthz 200 and /readyz ready in demo mode.
- Direct local server checks returned /healthz 200 and Dash HTTP 200 on http://127.0.0.1:8050.
- Playwright Chromium was installed and the browser smoke test passed against the local server, confirming the dashboard heading and synthetic-data banner.
- Both Compose files passed docker compose config validation.
- Source includes separate ARM64 Mac app Compose, x86-64 SQL Server Compose, Codespaces setup, SQL migrations, production Dockerfile, GitHub Actions, Bicep, MCP, token exchange, benchmark, and legacy example.

## Pending or unverified

- External SQL Server was not configured. Needed: reachable host/IP and port, database name, application login/password or Entra/managed identity plan, TLS certificate chain, and firewall/VPN access. The app will use SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD, SQL_ENCRYPT=true, and SQL_TRUST_SERVER_CERTIFICATE=false.
- Docker Desktop was later available. Separate ARM64 and AMD64 builds completed successfully. Both images passed architecture metadata checks, required Python/MCP imports, ODBC Driver 18 checks, `/healthz`, and Dash HTTP smoke checks. The x86 SQL Server Developer image was not fully pulled on the M2 because it is intentionally an x86-only external development dependency; full SQL Compose startup, migrations, restart persistence, and backup/restore remain pending on the intended x86-64 Linux/Proxmox host.
- Azure deployment, ACR, Container Apps, OIDC, Entra, Claude, and remote MCP are configuration-only until credentials and authorization are supplied.
- SQL Server-backed integration tests and real T-SQL benchmark timing/logical reads are pending external SQL Server access.

## Commands for remaining gates

    ./scripts/start-demo.sh
    python -m playwright install chromium
    pytest tests/browser -q
    docker build --platform linux/arm64 -t harvestops:arm64 .
    docker build --platform linux/amd64 -t harvestops:amd64 .
    SQLSERVER_MIGRATION_CONNECTION='...' python db/run_migrations.py
    SQLSERVER_MIGRATION_CONNECTION='...' python scripts/benchmark_sql.py
