# AG Grid feature boundary

HarvestOps uses Dash AG Grid Community only. The required shipment board uses Community-compatible column definitions, sorting, filtering within the bounded server-returned page, resizable columns, and accessible Previous/Next controls backed by server-side SQL pagination. No Enterprise module, license key, or Enterprise-only API is required to run the application.

Enterprise alternatives are intentionally out of scope for this portfolio build. If a production program later licenses AG Grid Enterprise, suitable optional upgrades could include:

- Server-side row model for richer virtualized datasets and grouped remote queries.
- Set filters, advanced filter builder, pivoting, and aggregation for analyst workspaces.
- Column tool panels and state persistence for personalized operational views.
- Excel export and integrated charts where those capabilities are approved and licensed.

Those alternatives would require a licensing decision, dependency review, accessibility review, server-side query contracts, and separate test coverage. They must not be enabled by simply swapping imports: authorization, result bounds, export safeguards, and SQL performance limits remain application responsibilities.
