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

## Milestone 2 — data, security, and tests

- [x] SQL Server/Azure SQL schema, migrations, seed, views, and stored procedures
- [x] pyodbc repository with parameterized SQL and UTC policy
- [x] CSV validation/import with idempotency, staging semantics, and audit trail
- [x] Knowledge search with permission filtering and optional Claude adapter boundary
- [x] Signed-token exchange example with JOSE validation and replay store
- [x] Negative authorization and workflow tests
- [x] Retrieval evaluation fixture and benchmark harness

## Milestone 3 — delivery and examples

- [x] ARM64 development image and AMD64 deployment image definitions
- [x] Mac + external database Compose and full x86-64 development Compose
- [x] Codespaces devcontainer and one-command startup/test scripts
- [x] GitHub Actions checks, image tagging, OIDC/Azure deployment templates
- [x] Read-only MCP example and isolated legacy React sample
- [x] SQL performance case study and backup/restore/rollback guidance
- [x] SDLC, security, architecture, onboarding, UAT, and interview demo documentation

## Verification gates

- [ ] External SQL Server connection verified (blocked until connection details are provided)
- [ ] Docker daemon and ARM64/AMD64 image builds verified (Docker daemon unavailable at kickoff)
- [x] Python unit and service tests pass
- [x] Demo-mode runtime smoke test passes
- [x] Browser smoke test passes against the local demo server
- [~] Container smoke tests are scripted; execution pending Docker daemon availability
- [~] Azure deployment validation is configuration-only until credentials are supplied
