# Legacy shipment lookup parity

This sample is intentionally isolated from the main build. It demonstrates how a small
React lookup can be evaluated before migrating the workflow into the Dash application.

## Workflow mapping

| Concern | React sample | HarvestOps Dash equivalent | Verification boundary |
| --- | --- | --- | --- |
| Route/surface | Vite root page at `/` | Dash **Dock & shipment board** page | Both render a shipment-facing surface |
| Input | `Shipment ID` input, trimmed on change | Shipment board’s visible read-only lookup plus `/api/shipments/<shipment_id>` detail route | `SHP-1001` is the shared lookup fixture |
| Matching | Case-insensitive exact match in the local fixture | Server-side repository/service lookup by shipment ID | Detail endpoint is role-protected and returns 404 for a miss |
| Result | Customer, product, facility, and status | Visible lookup result and protected detail route expose the same business fields | Synthetic records are the source of truth for the demo |
| Empty/error state | “No shipment found.” after a non-empty miss | HTTP 404 JSON error and the board’s empty/failure states | No result is not treated as success |
| Authorization | Not implemented in this isolated read-only sample | Viewer/operator/admin server-side role checks | React is not a production security boundary |
| State changes | None | Status changes, import, and approvals remain in the Dash workflow | The migration sample deliberately has no write controls |
| Validation/state | Input normalization in component state | Service validation, optimistic concurrency, CSRF, and audit events | Full business controls stay in the main application |

## Recorded verification

Run from the repository root:

```bash
cd legacy
npm ci
npm run build
```

The recorded local result is a successful `npm ci`, successful Vite production build,
and a clean production dependency audit. The main application’s browser smoke suite
also verifies the equivalent Dash surface and authenticated shipment detail lookup:

```bash
./scripts/test-browser.sh
```

That browser suite is the evidence for the Dash side of the comparison; it does not
claim that the React sample has a browser automation suite of its own. The React sample
uses an in-file synthetic fixture and does not call SQL Server or an external API.

## Migration notes

Keeping this workflow in React would require an API boundary, shared validation and
authorization semantics, routing/state ownership, and a second build/deployment surface.
The Dash implementation keeps the lookup within the server-authorized shipment board,
SQL-side paging, audit/workflow callbacks, and one Python deployment surface. A future
migration can preserve the React presentation while moving the lookup to the existing
protected detail endpoint; it must not treat client-side filtering as authorization.

