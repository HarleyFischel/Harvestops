# Requirements and acceptance criteria

The tracked checklist is the implementation source of truth; this matrix explains the evidence expected at handoff. The [validation report](validation-report.md) records actual commands and separates verified controls from account-dependent gates.

## Locally verified acceptance

| Area | Acceptance evidence |
| --- | --- |
| Fresh demo | `./scripts/start-demo.sh` serves Dash on port 8050; `/healthz` and `/readyz` return success with an explicit synthetic-data indicator. |
| Dashboard | Seeded shipment, production, and labor records produce coherent KPIs; date, customer, product, and facility filters drive cards, charts, and exceptions together. |
| Shipment board | AG Grid Community renders shipment detail fields; server-side customer/product/facility/exception filters and bounded pagination work; status changes enforce role, transition, CSRF, and row-version rules. |
| Purchasing | Create, submit, approve, reject, history, decimal totals, self-approval prevention, authorization, and concurrency rules are covered by service/browser tests. |
| Ingestion | The sample CSV validates through staging semantics, applies one new record, reports one invalid record, and remains idempotent on repeat import. |
| Security | Demo and Entra modes are separate; protected routes/callbacks/exports/workflows fail closed; cookies, CSRF, SQL parameters, CSV safeguards, JWT replay checks, and provider-boundary authorization have negative tests. |
| Integrations | Local keyword retrieval, optional provider failure handling, official MCP stdio calls, portal-token exchange, legacy React build, and infrastructure rendering are executable without paid credentials. |
| Delivery | Python tests, browser tests, ARM64/AMD64 image builds, non-root container smoke checks, pinned image scans, Codespaces verification, and local rollback evidence are recorded. |

## External or account-dependent acceptance

These are implemented as reproducible configuration and tests but cannot be claimed as passed without the target environment:

- External x86-64 SQL Server: connectivity, migrations, SQL integration tests, restart persistence, backup/restore, and real benchmark timings.
- Azure: ACR push, Container Apps deployment, managed identity SQL access, Key Vault/Redis sessions, Entra login, migration-job execution, OIDC, and post-deployment smoke checks.
- Optional providers: Claude answer calls, Azure Data Factory execution, and remote MCP transport.

Required handoff evidence for those gates is listed in the pending section of the validation report. No SQLite fallback, SQL Server emulation on the Mac, cloud provisioning, or paid provider call is treated as a successful substitute.
