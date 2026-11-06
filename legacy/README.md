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

The full mapping, verification boundary, and migration trade-offs are recorded in
[`feature-parity.md`](feature-parity.md) and [`../docs/validation-report.md`](../docs/validation-report.md). The React
sample uses the same synthetic shipment IDs as the main app, but it is intentionally
read-only and is not a production authorization boundary.
