# Data dictionary

| Table/view | Purpose | Key fields |
| --- | --- | --- |
| facilities | Growing/packing locations | facility_id, facility_code |
| customers | Buyers | customer_id, customer_name |
| products | Produce and UOM | product_id, sku, uom |
| shipments | Operational loads | shipment_id, status, ordered_qty, shipped_qty, UTC timestamps, row_version |
| shipment_lines | Product quantities | shipment_line_id, shipment_id |
| dock_appointments | Dock schedule | appointment_id, shipment_id, dock_code |
| production_runs | Output/labor | run_date, output_qty, labor_hours |
| purchase_requests/lines | Approval workflow | request_id, status, version_no, quantity, unit_cost |
| audit_events | Immutable business history | actor, action_name, entity_id, detail_json |
| import_runs/errors | Ingestion trace | status, applied_count, rejected_count |
| knowledge_documents/roles | Search corpus and access | sensitivity, role_name |

Key constraints enforce positive quantities, shipped <= ordered, valid workflow statuses, foreign-key integrity, and decimal precision.

## Relationship diagram

```mermaid
erDiagram
  FACILITIES ||--o{ SHIPMENTS : handles
  CUSTOMERS ||--o{ SHIPMENTS : orders
  PRODUCTS ||--o{ SHIPMENTS : contains
  CARRIERS ||--o{ SHIPMENTS : hauls
  SHIPMENTS ||--o{ SHIPMENT_LINES : has
  SHIPMENTS ||--o{ DOCK_APPOINTMENTS : schedules
  FACILITIES ||--o{ PRODUCTION_RUNS : runs
  PRODUCTS ||--o{ PRODUCTION_RUNS : produces
  FACILITIES ||--o{ PURCHASE_REQUESTS : scopes
  PURCHASE_REQUESTS ||--o{ PURCHASE_REQUEST_LINES : contains
  PRODUCTS ||--o{ PURCHASE_REQUEST_LINES : requested
  IMPORT_RUNS ||--o{ IMPORT_ERRORS : records
  KNOWLEDGE_DOCUMENTS ||--o{ KNOWLEDGE_DOCUMENT_ROLES : permits
```
