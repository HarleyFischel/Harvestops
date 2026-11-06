# HarvestOps implementation checklist

This checklist is the source of truth for the build. `[x]` means implemented and locally checked; `[~]` means implemented but dependent on an unavailable external service; `[ ]` means not complete.

## Milestone 1 — core application

- [x] Repository checkout and baseline inspection
- [x] Central configuration and structured logging
- [x] Deterministic synthetic domain data and KPI calculations
- [x] Flask + Plotly Dash shell with original HarvestOps styling
- [x] Dashboard filters, KPI cards, Plotly charts, and shipment exceptions
- [x] Shipment board with filtering, pagination, status transitions, concurrency checks, export
- [x] Purchasing request, submit, approve/reject, self-approval prevention, and history
- [x] Demo authentication with server-side role checks
- [x] Health/readiness endpoints and startup diagnostics
- [x] SQL Server-backed service adapter selected by STORAGE_MODE=sqlserver
- [x] Viewer-protected shipment detail endpoint with current optimistic-concurrency version
- [x] Shipment CSV upload/API workflow with validation, idempotency, CSRF token check, and repository sample fixture

## Milestone 2 — data, security, and tests

- [x] SQL Server/Azure SQL schema, migrations, seed, views, and workflow stored procedure
- [x] Staging import table/procedure and ADF mapping template
- [x] pyodbc repository with parameterized SQL and UTC policy
- [x] SQL login mode for external SQL Server and Azure SQL managed-identity access-token mode
- [x] CSV validation/import with idempotency, staging semantics, and audit trail
- [x] Knowledge search with permission filtering and optional Claude adapter boundary
- [x] Signed-token exchange example with JOSE validation and replay store
- [x] Negative authorization and workflow tests
- [x] Portal token tamper, expiry, audience, and replay tests
- [x] Retrieval evaluation fixture and benchmark harness

## Milestone 3 — delivery and examples

- [x] ARM64 development image and AMD64 deployment image definitions and separate builds
- [x] Mac + external database Compose and full x86-64 development Compose
- [x] Codespaces devcontainer and one-command startup/test scripts
- [x] GitHub Actions checks, image tagging, OIDC/Azure deployment templates
- [x] Read-only MCP example and isolated legacy React sample
- [x] SQL performance case study and backup/restore/rollback guidance
- [x] SDLC, security, architecture, onboarding, UAT, and interview demo documentation

## Verification gates

- [ ] External SQL Server connection verified (blocked until connection details are provided)
- [x] Docker daemon and ARM64/AMD64 image builds verified
- [x] Python unit and service tests pass (51 passed, 2 SQL integration tests skipped without connection details)
- [x] Demo-mode runtime smoke test passes
- [x] Browser smoke test passes against the local demo server (6 tests, repeated twice)
- [x] ARM64 and AMD64 application container health/Dash smoke tests
- [~] Full x86 SQL Server Compose runtime, migration, persistence, and backup/restore exercise pending on the intended x86-64 host
- [~] Azure deployment validation is configuration-only until credentials are supplied
