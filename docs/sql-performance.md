# SQL performance case study

Run the executable benchmark only against a disposable SQL Server database:

```bash
SQLSERVER_MIGRATION_CONNECTION='DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=HarvestOps;UID=...;PWD=...;Encrypt=yes;TrustServerCertificate=no;' \
python scripts/benchmark_sql.py
```

The script generates 100,000 synthetic shipment rows, reports the SQL Server version and row count, compares a deliberately non-sargable `CONVERT(date, planned_departure_utc)` predicate with a range predicate, verifies matching grouped results, creates a covering `(status, planned_departure_utc)` index, and measures the indexed query. `SET STATISTICS IO/TIME` messages are printed when the driver exposes them.

Capture elapsed time, logical reads, execution plans, SQL version, dataset size, hardware, and warm/cold-cache conditions in the validation report. No improvement percentage is claimed until the benchmark runs against the intended SQL Server; Query Store or an actual execution plan should be used for production tuning.
