# Legacy React shipment lookup

This isolated sample reproduces the read-only shipment-ID lookup workflow using the same synthetic records as the main application.

```bash
npm install
npm run dev
npm run build
```

Feature parity: both samples accept a shipment ID, show customer/product/facility/status for a match, show a no-result state, and perform no writes. The Dash equivalent is the shipment board in the main app. Migration trade-offs: Dash keeps server-side authorization, SQL paging, audit/workflow callbacks, and one Python deployment surface; React offers independently deployable client routing/state but would need an API boundary, shared validation, and additional operational ownership for parity.
