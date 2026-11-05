# UAT checklist

- [ ] Start from a fresh clone and open the forwarded private port.
- [ ] Confirm synthetic-data indicator, dashboard filters, KPI calculations, chart updates, and exception rows.
- [ ] As `demo.viewer`, confirm shipment changes and exports are denied.
- [ ] As `demo.operator`, apply an allowed transition, retry a stale version, upload the sample CSV, and repeat it.
- [ ] Create and submit a purchase request; approve it as another user; verify self-approval and stale decisions fail.
- [ ] Search knowledge locally and verify citations; verify Claude mode fails clearly without credentials.
- [ ] Run `/healthz` and `/readyz`; inspect audit/import history.
- [ ] On x86-64, run migrations, restart the stack, and verify persisted records.
