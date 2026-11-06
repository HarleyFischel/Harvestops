# Validation report

Date: 2026-11-05. Host: Apple Silicon M2, 8 GiB RAM, macOS, Python 3.12 virtual environment. Disk: approximately 170 GiB free at start. Docker CLI/server 29.8.0, Docker Desktop, and an ARM64 daemon were available after the initial inspection.

## Completed evidence

- Repository connected to https://github.com/HarleyFischel/Harvestops.git; initial commit was 85be7ca.
- pip install -e '.[dev]' completed in .venv312 using Python 3.12.
- `scripts/init-env.sh` was syntax-checked and exercised in a temporary directory; it generated a mode-600 `.env` secret and refused to overwrite an existing file.
- `.venv312/bin/python -m pytest -q` previously passed: 41 tests, with 2 SQL integration tests skipped because no connection string was supplied.
- Refreshed locked dependencies were installed into `.venv`; `PYTHON_BIN=.venv/bin/python ./scripts/test.sh` now passes 42 tests with 2 SQL integration tests skipped, followed by passing Ruff lint and format checks. The security-sensitive pins include PyJWT 2.14.0, cryptography 50.0.0, MCP 1.28.1, MSAL 1.39.0, and Pydantic 2.12.5.
- `./scripts/verify-local.sh` now passes with 42 passed / 2 skipped and a redacted configuration summary; it printed seeded KPIs of 8 shipments, 66.6667% on-time, 97.6471% fill rate, $13,165 freight, 33,825 production units, and 42.5 units/hour. The script prefers an existing `.venv312` or `.venv` interpreter before host Python.
- ruff check . passed.
- `ruff format --check .` passed after formatting the repository; CI now runs the same blocking format check.
- `uvx --from pip-audit==2.9.0 pip-audit --strict` completed locally with `No known vulnerabilities found`.
- Flask test-client smoke checks returned /healthz 200 and /readyz ready in demo mode.
- Direct local server checks returned /healthz 200 and Dash HTTP 200 on http://127.0.0.1:8050.
- Playwright Chromium was installed and browser smoke passed 6 tests against the local server: desktop dashboard/date-range rendering, shipment-board and purchasing-screen surfaces, an authenticated shipment status workflow including confirmation, a purchase approval workflow, 390px mobile and 768px tablet responsive-content checks, and a visible keyboard/programmatic focus indicator check.
- The same 6 browser smoke tests were rerun twice against the refreshed `.venv` application after the workflow/API and responsive styling changes and passed both times.
- Legacy React sample passed `npm ci` and `npm run build`; production dependency audit reported no vulnerabilities. The isolated sample uses exact React/Vite pins and a package lock.
- `uv lock` and a hash-pinned `requirements.lock` were generated; the production Dockerfile installs from the lock before installing the application package.
- A temporary Redis 7 container verified the production-style `SESSION_REDIS_URL` mode, demo login, session-bound CSRF token, and readiness behavior; the temporary container was removed afterward.
- The ARM64 `Dockerfile.dev` image built from `requirements-dev.lock` and its startup command passed `/healthz` and Dash HTTP smoke checks.
- The production ARM64 image `harvestops:arm64-final2` and AMD64 image `harvestops:amd64-final2` both built from the refreshed lock and latest source. Pinned Trivy 0.58.1 scanning of the AMD64 image archive reported `Total: 0 (HIGH: 0, CRITICAL: 0)` for the Debian layer and no Python findings; pip was removed from the runtime layer after installation because it is not required by the application.
- The same pinned Trivy scan of the ARM64 image archive also reported `Total: 0 (HIGH: 0, CRITICAL: 0)` with no Python findings.
- After correcting the production package-install order and bundling `data/sample-shipment-updates.csv`, fresh `harvestops:arm64-sample-fix` (`sha256:df853fdb5b495fa56b22a4e9ce0cfebd832d9ccbb6fdca51534417f1889ec6a3`) and `harvestops:amd64-sample-fix` (`sha256:d2e93e5df75e36ec2fc1536d8e9b054f8b1e14e24c1e8665cebd18f3ae260e4f`) images rebuilt independently. Both disposable containers returned `/healthz` and `/readyz` successfully, served the Dash root with HTTP 200, imported the installed application modules, contained the sample CSV, ran as non-root `appuser`, and reported `arm64/linux` and `amd64/linux` respectively. Pinned Trivy 0.58.1 scans of both refreshed images reported `Total: 0 (HIGH: 0, CRITICAL: 0)`.
- Local rollback exercise passed: the prior local ARM64 image and the current final ARM64 image each served `/healthz` 200 and root HTTP 200 on the same port in succession; temporary containers were removed.
- MCP tool tests passed locally for lookup, KPI definitions, exception result limits, unknown-principal rejection, and exposed-mode RS256 authentication; no remote MCP deployment was claimed.
- The official MCP stdio runtime was exercised locally with a JSON-RPC `initialize`, `tools/list`, and `tools/call` exchange. It reported protocol `2025-06-18`, exposed `lookup_shipment`, `list_shipment_exceptions`, and `approved_kpi_definitions`, and returned seeded shipment `SHP-1004` for `demo.operator`; remote MCP remains unverified.
- GitHub Actions YAML parsed locally; the CI workflow now installs the hash-pinned development lock before the editable project, contains dependency/secret checks, blocking AMD64 image scanning, an explicit Dash readiness wait before browser tests, and a reproducible legacy React build/audit job, plus an opt-in SQL Server service job gated by repository variable `SQLSERVER_INTEGRATION_ENABLED=true` and the `SQLSERVER_TEST_PASSWORD` secret. The release workflow performs federated ACR login, explicit AMD64 image publishing, immutable digest update, and smoke check.
- The official Azure CLI container installed Bicep CLI v0.48.1 and compiled the updated `infra/main.bicep` successfully; the template now wires production identity/session settings and Key Vault secret access through a least-privilege managed-identity role assignment. No Azure deployment or resource provisioning was performed.
- `infra/parameters.dev.json`, `infra/parameters.staging.json`, and `infra/parameters.prod.json` all parse successfully and cover every required Bicep parameter; they contain placeholders only and no credentials.
- The ADF template now explicitly adds the pipeline `import_run_id` to each staged row and avoids shared-table truncation; local JSON validation passed, but ADF deployment and execution remain unverified.
- The unverified ADF example now includes a separate UTC hourly `ScheduleTrigger` template that passes a deterministic run id expression to the pipeline; both ADF JSON files parse locally.
- A tracked-file secret-pattern scan found no private-key, common API-key, or credential-file matches; the repository's hosted Gitleaks job remains the authoritative CI check.
- `docker compose config -q` passed for `compose.mac.yml`, `compose.x86.yml`, and `docker-compose.yml` using an ephemeral validation password.
- The web app now selects `SqlServerStore` when `STORAGE_MODE=sqlserver`; the adapter uses parameterized queries, SQL-side paging/counts, transactions, rowversion checks, and audit inserts. This code path is implementation-checked but not live-connection verified.
- SQL shipment imports now stage parsed rows in `staging.shipment_updates` and execute the versioned validation/apply procedure before reporting applied and rejected rows; this implementation path is not live-connection verified.
- The shipment board now displays import freshness (source, status, UTC timestamp, applied count, and rejected count) for both demo and SQL stores and refreshes it after a successful upload; the demo freshness transition is covered by a service test.
- The shipment board now displays bounded import-run history and individual rejected rows after uploads; service and callback-registration tests cover the report path.
- `data/sample-shipment-updates.csv` is an upload-ready synthetic fixture with one new record, one existing/idempotent record, and one invalid record; the service test verifies the expected applied, repeated, and rejected results.
- The viewer-protected `/api/shipments/<shipment_id>` detail route returns current status and optimistic-concurrency version for authorized clients; direct unauthorized and not-found behavior are covered by tests.
- Production configuration now fails closed unless storage is SQL Server, SQL encryption is enabled, and `TrustServerCertificate` is disabled; structured log formatting redacts common secret-shaped key/value messages.
- SQL migrations 003–007 add the shipment-status and staged-import procedures/tables, pending-purchase/knowledge seed records, and SQL/demo seed-departure alignment; procedure execution is pending the external SQL Server gate.
- The deterministic local retrieval evaluation passed 4/4 exact-source checks; see `docs/retrieval-evaluation.md`.
- Dashboard KPI scope now includes planned-departure date range and seeded production-run/labor records; the date-scope service test passed.
- Entra identity claims are reconstructed from the server-side session for multi-worker requests; direct unauthenticated Dash requests, CSRF-protected demo account switching, and cross-user purchasing reads have negative coverage.
- Portal-token tests cover RS256 tampering, expiry, issuer/audience, single-use replay, and the Redis-backed atomic replay-store option; external Redis deployment is not verified.
- MCP store selection now follows `STORAGE_MODE`, keeping local demo calls on synthetic data while routing configured SQL deployments through `SqlServerStore`; the selection branch is directly covered by local tests and no remote MCP deployment is claimed.
- Source includes separate ARM64 Mac app Compose, x86-64 SQL Server Compose, Codespaces setup, SQL migrations, production Dockerfile, GitHub Actions, Bicep, MCP, token exchange, benchmark, and legacy example.

## Pending or unverified

- External SQL Server was not configured. The local `.env` still contains the example endpoint `host.example.internal,1433`; a connection attempt was not claimed as successful. Needed: reachable host/IP and port, database name, application login/password or Entra/managed identity plan, TLS certificate chain, and firewall/VPN access. The app will use SQL_SERVER, SQL_DATABASE, SQL_USER, SQL_PASSWORD, SQL_ENCRYPT=true, and SQL_TRUST_SERVER_CERTIFICATE=false. The host Python environment also lacks the unixODBC runtime; the application images include ODBC Driver 18 and unixODBC.
- Separate ARM64 and AMD64 builds completed successfully. `harvestops:arm64-final2` produced image id `sha256:b20bb44b0233e883fb5e24a816d8c8d4285441b5674093d25d3ff9a2e0ad6ad2`; `harvestops:amd64-final2` produced image id `sha256:d86e3272e44d6dbd1e1158eea7cee23fced5b6aa75265c4d85e566720ecfc82f`. `docker image inspect` reported `arm64 linux` and `amd64 linux`; disposable containers for both architectures returned `/healthz` and `/readyz`, imported Dash/AG Grid/Flask/MCP/pyodbc, reported unixODBC, contained current SQL/knowledge/static assets, and ran as UID 10001. The x86 SQL Server Developer image was not fully pulled on the M2 because it is intentionally an x86-only external development dependency; full SQL Compose startup, migrations, restart persistence, and backup/restore remain pending on the intended x86-64 Linux/Proxmox host.
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
