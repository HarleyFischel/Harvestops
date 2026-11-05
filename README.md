# HarvestOps

HarvestOps is a synthetic produce-operations portfolio application built with Python, Flask, Plotly Dash, Dash AG Grid Community, Plotly, SQL Server-compatible T-SQL, Docker, and gunicorn. It is original branding and is not affiliated with Pero Family Farms.

## Fresh local demo

Supported Python: 3.11–3.13. Python 3.12 is recommended.

    cp .env.example .env
    python3.12 -m venv .venv
    . .venv/bin/activate
    pip install -e '.[dev]'
    ./scripts/start-demo.sh

For reproducible runtime dependency resolution, `requirements.lock` is exported from `uv.lock`; use `uv sync --locked` when uv is available.

Open http://127.0.0.1:8050. Demo accounts are demo.viewer, demo.operator, demo.approver, and demo.admin. The role selector is development-only but server-side authorization is still enforced.

## Codespaces

Open the repository in GitHub Codespaces. The devcontainer installs dependencies, enables Docker through the Docker-in-Docker feature, forwards private port 8050, and runs the demo. Verify Docker with `docker version`; use `./scripts/test.sh` for tests. Stop/restart the process with Ctrl-C and `./scripts/start-demo.sh`; rebuild the container from the Codespaces command palette. Deleting the Codespace removes its local filesystem; deleting the Docker volume in a database environment destroys the SQL Server data unless restored from backup.

## Containers and database modes

The M2 Mac application image is ARM64 and uses an external database:

    cp .env.example .env
    # Set STORAGE_MODE=sqlserver and SQL_SERVER to the x86-64 Linux/Proxmox host.
    docker compose -f compose.mac.yml up --build

No SQL Server emulation is required or started on the Mac. The SQL Server Developer container is only in the x86-64 stack:

    MSSQL_SA_PASSWORD='Use-a-long-local-only-password!' docker compose -f compose.x86.yml up --build

The x86 stack is for an x86-64 Linux host/VM and persists SQL Server data in sqlserver-data. Apply migrations with SQLSERVER_MIGRATION_CONNECTION='...' python db/run_migrations.py. Local TrustServerCertificate=true is only for the documented development container; production must use certificate verification.

## What is implemented

- Operations dashboard: date-range/customer/product/facility filters, KPI cards, linked Plotly charts, and exception table.
- Shipment board: service filtering/paging, allowed status transitions, optimistic version checks, role-protected CSV export, and audit events.
- Purchasing: decimal totals, submit/approve/reject workflow, self-approval prevention, concurrency checks, and audit events.
- Knowledge assistant: permission-safe local search with citations; optional provider boundary is documented.
- CSV ingestion: validation, rejected rows, idempotent repeats, run history, and synthetic sample.
- Demo identity plus fail-closed Entra/MSAL adapter; secure session cookie settings.
- SQL Server/Azure SQL migrations, seed data, view, stored procedure pattern, schema/data dictionary, and pyodbc adapter.
- Read-only official MCP SDK tools, signed-token exchange example, React legacy lookup, benchmark harness, Compose, Codespaces, GitHub Actions, and Azure Container Apps Bicep.

AG Grid Community is the only required grid feature. Enterprise features are not used.

See docs/validation-report.md for actual evidence and unverified gates.

Leadership and delivery references: [project charter](docs/project-charter.md), [developer onboarding](docs/developer-onboarding.md), [UAT checklist](docs/uat-checklist.md), [skills evidence](docs/skills-evidence.md), and [release checklist](docs/change-management.md).
