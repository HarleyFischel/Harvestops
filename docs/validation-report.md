# Validation report

Date: 2026-11-05. Host: Apple Silicon M2, 8 GiB RAM, macOS, Python 3.12 virtual environment. Disk: approximately 170 GiB free at start. Docker CLI/server 29.8.0, Docker Desktop, and an ARM64 daemon were available after the initial inspection.

## Completed evidence

- Repository connected to https://github.com/HarleyFischel/Harvestops.git; initial commit was 85be7ca.
- pip install -e '.[dev]' completed in .venv312 using Python 3.12.
- `.venv312/bin/python -m pytest -q` passed: 29 tests, with 1 SQL integration test skipped because no connection string was supplied.
- ruff check . passed.
- Flask test-client smoke checks returned /healthz 200 and /readyz ready in demo mode.
- Direct local server checks returned /healthz 200 and Dash HTTP 200 on http://127.0.0.1:8050.
- Playwright Chromium was installed and the browser smoke test passed against the local server, confirming the dashboard heading and synthetic-data banner.
- Legacy React sample passed `npm ci` and `npm run build`; production dependency audit reported no vulnerabilities. The isolated sample uses exact React/Vite pins and a package lock.
- `uv lock` and a hash-pinned `requirements.lock` were generated; the production Dockerfile installs from the lock before installing the application package.
- A temporary Redis 7 container verified the production-style `SESSION_REDIS_URL` mode, demo login, session-bound CSRF token, and readiness behavior; the temporary container was removed afterward.
- The ARM64 `Dockerfile.dev` image built from `requirements-dev.lock` and its startup command passed `/healthz` and Dash HTTP smoke checks.
- MCP tool tests passed locally for authenticated lookup, KPI definitions, exception result limits, and unknown-principal rejection; no remote MCP deployment was claimed.
- GitHub Actions YAML parsed locally; the CI workflow now contains an SQL Server service job gated by the repository's `SQLSERVER_TEST_PASSWORD` secret, and the release workflow performs federated ACR login, immutable digest update, and smoke check.
- Official Bicep CLI compiled `infra/main.bicep` successfully; no Azure deployment or resource provisioning was performed.
- `docker compose config -q` passed for `compose.mac.yml`, `compose.x86.yml`, and `docker-compose.yml` using an ephemeral validation password.
- The web app now selects `SqlServerStore` when `STORAGE_MODE=sqlserver`; the adapter uses parameterized queries, SQL-side paging/counts, transactions, rowversion checks, and audit inserts. This code path is implementation-checked but not live-connection verified.
- SQL migrations 003 and 004 add the shipment-status and staged-import procedures/tables; procedure execution is pending the external SQL Server gate.
- The deterministic local retrieval evaluation passed 4/4 exact-source checks; see `docs/retrieval-evaluation.md`.
- Dashboard KPI scope now includes planned-departure date range and seeded production-run/labor records; the date-scope service test passed.
- Entra identity claims are reconstructed from the server-side session for multi-worker requests; direct unauthenticated Dash requests and cross-user purchasing reads have negative coverage.
- Source includes separate ARM64 Mac app Compose, x86-64 SQL Server Compose, Codespaces setup, SQL migrations, production Dockerfile, GitHub Actions, Bicep, MCP, token exchange, benchmark, and legacy example.

## Pending or unverified

- External SQL Server was not configured. The local `.env` still contains the example endpoint `host.example.internal,1433`; a connection attempt was not claimed as successful. Needed: reachable host/IP and port, database name, application login/password or Entra/managed identity plan, TLS certificate chain, and firewall/VPN access. The app will use SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD, SQL_ENCRYPT=true, and SQL_TRUST_SERVER_CERTIFICATE=false. The host Python environment also lacks the unixODBC runtime; the application images include ODBC Driver 18 and unixODBC.
- Separate ARM64 and AMD64 builds completed successfully. `docker image inspect` reported `arm64 linux` and `amd64 linux`; both images passed required Python/MCP imports, ODBC Driver 18/module checks, `/healthz`, and Dash HTTP smoke checks in separate containers. The x86 SQL Server Developer image was not fully pulled on the M2 because it is intentionally an x86-only external development dependency; full SQL Compose startup, migrations, restart persistence, and backup/restore remain pending on the intended x86-64 Linux/Proxmox host.
- Playwright browser smoke passed against the running local server for the dashboard plus shipment-board and purchasing-screen workflow surfaces, and a 390px mobile viewport check found both the dashboard heading and synthetic-data indicator.
- Azure deployment, ACR, Container Apps, OIDC, Entra, Claude provider calls, and remote MCP are configuration-only until credentials and authorization are supplied. The local Claude adapter and MCP tool code are implemented and unit/runtime import checked; remote calls were not claimed.
- SQL Server-backed integration tests and real T-SQL benchmark timing/logical reads are pending external SQL Server access. The new migration 005 validation procedure is implemented but not executed against SQL Server.

## Commands for remaining gates

    ./scripts/start-demo.sh
    python -m playwright install chromium
    pytest tests/browser -q
    docker build --platform linux/arm64 -t harvestops:arm64 .
    docker build --platform linux/amd64 -t harvestops:amd64 .
    SQLSERVER_MIGRATION_CONNECTION='...' python db/run_migrations.py
    SQLSERVER_MIGRATION_CONNECTION='...' python scripts/benchmark_sql.py

## Evidence not available in this environment

No external SQL Server connection details were supplied. The remaining SQL gate needs the Proxmox host/IP and port, a database/login or Entra authentication plan, firewall/VPN reachability, and the TLS certificate chain. Azure deployment, ACR, Container Apps, Entra, Claude, and remote MCP remain configuration-only until credentials and authorization are supplied. No cloud resources were provisioned.
