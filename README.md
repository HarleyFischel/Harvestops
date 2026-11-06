# HarvestOps

HarvestOps is a synthetic produce-operations portfolio application built with Python, Flask, Plotly Dash, Dash AG Grid Community, Plotly, SQL Server-compatible T-SQL, Docker, and gunicorn. It is original branding and is not affiliated with Pero Family Farms.

## Fresh local demo

Supported Python: 3.11–3.13. Python 3.12 is recommended.

    ./scripts/init-env.sh
    python3.12 -m venv .venv
    . .venv/bin/activate
    pip install -e '.[dev]'
    ./scripts/start-demo.sh

For reproducible runtime dependency resolution, `requirements.lock` is exported from `uv.lock`; use `uv sync --locked` when uv is available.

Open http://127.0.0.1:8050. Demo accounts are demo.viewer, demo.operator, demo.approver, and demo.admin. The role selector is development-only but server-side authorization is still enforced.

## Codespaces

Open the repository in GitHub Codespaces. The devcontainer installs dependencies, enables Docker through the Docker-in-Docker feature, forwards private port 8050, and runs the demo. Verify Docker with `docker version`; use `./scripts/verify-codespaces.sh` for a one-command local verification (set `RUN_BROWSER=true` after installing Playwright Chromium). Use `./scripts/test.sh` for tests. Stop/restart the process with Ctrl-C and `./scripts/start-demo.sh`; rebuild the container from the Codespaces command palette. Deleting the Codespace removes its local filesystem; deleting the Docker volume in a database environment destroys the SQL Server data unless restored from backup.

## Containers and database modes

The M2 Mac application image is ARM64 and uses an external database:

    ./scripts/init-env.sh
    # Set STORAGE_MODE=sqlserver, SQL_AUTH_MODE=sql_login, and SQL_SERVER to the x86-64 Linux/Proxmox host.
    docker compose -f compose.mac.yml up --build

The normal Mac profile does not require or start SQL Server emulation. The SQL Server Developer container is also available in the complete x86-64 stack:

    MSSQL_SA_PASSWORD='Use-a-long-local-only-password!' docker compose -f compose.x86.yml up --build

The x86 stack is for an x86-64 Linux host/VM and persists SQL Server data in sqlserver-data. Its one-shot `database-init` service creates the configured database on a fresh volume, then the one-shot `migrations` service applies versioned T-SQL before the app starts; rerun migrations with `docker compose -f compose.x86.yml run --rm migrations` when needed. Local `SQL_ENCRYPT=false` and `TrustServerCertificate=true` are only for this documented development container; production must use encryption and certificate verification.

For a temporary M2-only SQL Server experiment, use the isolated emulated profile. It keeps SQL Server on an internal Docker network, publishes the ARM64 app on loopback port 8051, stores SQL data in the named `harvestops-mac-sql-data` volume, and creates a dedicated `harvestops_app` login before migrations:

    ./scripts/init-mac-sql-env.sh
    ./scripts/start-mac-sql-emulated.sh

Open http://127.0.0.1:8051. SQL Server Developer runs as `linux/amd64` under Docker Desktop emulation and is for nonproduction development only; Microsoft does not support this architecture combination. The bounded startup helper waits up to 45 minutes and prints service diagnostics on failure. Stop without deleting data with `docker compose --env-file .env.mac-sql -f compose.mac-sql-emulated.yml down`; `down -v` deletes the temporary SQL volume and database, so back up first. The external-database Mac profile and x86-64 profile remain separate. Run `./scripts/backup-restore-mac-sql.sh` for a copy-only backup and disposable restore smoke test; the backup is written under ignored `./backups`.

After verifying the temporary SQL profile, the local endpoint can be switched to the SQL-backed instance by stopping the demo process on port 8050, changing the ignored `HARVESTOPS_MAC_SQL_APP_PORT` in `.env.mac-sql` from `8051` to `8050`, and running `./scripts/start-mac-sql-emulated.sh`. This preserves any existing Cloudflare Tunnel configuration that already targets localhost:8050, but the public hostname must be checked separately. To return to the demo, stop the Mac SQL Compose profile, restore the ignored port value to `8051`, and run `./scripts/start-demo.sh`.

For the Mac external database, apply migrations explicitly after reviewing `.env`: `docker compose -f compose.mac.yml run --rm app python db/run_migrations.py`.

To preflight the external database from the ARM64 Mac application image, run `./scripts/verify-external-sql.sh` after configuring `.env`. It performs a TLS/configuration check and `SELECT DB_NAME()` against the configured server without starting SQL Server locally. Add `RUN_MIGRATIONS=true` only when you have reviewed and authorized applying the versioned migrations.

Validate infrastructure configuration without Azure credentials with `./scripts/verify-infrastructure.sh`. It renders all Compose files, validates ADF and parameter JSON, checks shell syntax, and compiles the Bicep template in the official Azure CLI container; it does not authenticate or provision resources.

On the x86-64 development host, run `MSSQL_SA_PASSWORD='...' ./scripts/backup-restore-x86.sh` for a repeatable backup/restore exercise. It copies a timestamped backup into `./backups`, replaces only the disposable `HarvestOps_restore` database, and runs read-only shipment/migration smoke queries. Review and protect the copied backup; do not use this script as a production backup policy.

Stop and restart Compose services with `docker compose -f compose.x86.yml stop` and `docker compose -f compose.x86.yml start` (or use the equivalent `compose.mac.yml` command). Use `docker compose ... down` to remove the containers while retaining named volumes. `docker compose -f compose.x86.yml down -v` deletes the `sqlserver-data` volume and destroys the local SQL Server database unless it has been backed up.

## What is implemented

- Operations dashboard: date-range/customer/product/facility filters, KPI cards, linked Plotly charts, and exception table.
- Shipment board: service filtering/paging, allowed status transitions, optimistic version checks, role-protected CSV export, and audit events.
- Purchasing: decimal totals, submit/approve/reject workflow, self-approval prevention, concurrency checks, and audit events.
- Knowledge assistant: permission-safe local search with citations; optional provider boundary is documented.
- CSV ingestion: validation, rejected rows, idempotent repeats, run history, and synthetic sample.
- Demo identity plus fail-closed Entra/MSAL adapter; secure session cookie settings.
- SQL Server/Azure SQL migrations, seed data, view, stored procedure pattern, schema/data dictionary, and pyodbc adapter.
- External SQL login mode plus Azure SQL managed-identity access-token mode; production SQL connections require encryption and certificate verification.
- Read-only official MCP SDK tools, signed-token exchange example, React legacy lookup, benchmark harness, Compose, Codespaces, GitHub Actions, and Azure Container Apps Bicep.

AG Grid Community is the only required grid feature. Enterprise features are not used; see [the grid feature boundary](docs/ag-grid.md) for separately documented alternatives.

See docs/validation-report.md for actual evidence and unverified gates.

The upload-ready fixture is `data/sample-shipment-updates.csv`. It demonstrates one new
shipment, one existing shipment that is safely treated as idempotent, and one rejected
invalid record. In demo mode, use the shipment board's **Upload shipment CSV** control
after signing in as `demo.operator` or `demo.admin`.

Leadership and delivery references: [project charter](docs/project-charter.md), [developer onboarding](docs/developer-onboarding.md), [UAT checklist](docs/uat-checklist.md), [skills evidence](docs/skills-evidence.md), [10-minute interview demo](docs/demo-script.md), and [release checklist](docs/change-management.md).

Integration references: [identity modes](docs/identity.md), [knowledge assistant](docs/knowledge-assistant.md), [knowledge document security](docs/knowledge-security.md), [MCP](docs/mcp.md), [portal token exchange](docs/portal-token.md), and [SQL performance case study](docs/sql-performance.md).
