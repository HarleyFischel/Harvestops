# Legacy React shipment lookup

This isolated sample reproduces the read-only shipment-ID lookup workflow using the same synthetic records as the main application.

```bash
npm install
npm run dev
npm run build
```

Feature-parity checklist:

- [x] Accept a shipment ID and normalize the lookup input.
- [x] Show customer, product, facility, and status for a matching record.
- [x] Show an explicit no-result state.
- [x] Perform read-only work with no write controls.
- [x] Provide the equivalent Dash workflow in the main application’s shipment board.

Verification is recorded in `docs/validation-report.md`: `npm ci`, `npm run build`, and the production dependency audit passed. Migration trade-offs: Dash keeps server-side authorization, SQL paging, audit/workflow callbacks, and one Python deployment surface; React offers independently deployable client routing/state but would need an API boundary, shared validation, and additional operational ownership for parity.
