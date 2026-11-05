"""Executable SQL performance case study; requires an external SQL Server."""
import os
import time

import pyodbc

CONNECTION = os.environ.get("SQLSERVER_MIGRATION_CONNECTION")
if not CONNECTION:
    raise SystemExit("Set SQLSERVER_MIGRATION_CONNECTION before running this benchmark")

with pyodbc.connect(CONNECTION, autocommit=True) as conn:
    cur = conn.cursor()
    cur.execute("IF OBJECT_ID('dbo.benchmark_shipments','U') IS NOT NULL DROP TABLE dbo.benchmark_shipments; CREATE TABLE dbo.benchmark_shipments(id bigint IDENTITY PRIMARY KEY, customer_id int NOT NULL, planned_departure_utc datetime2 NOT NULL, status varchar(30) NOT NULL, shipped_qty int NOT NULL)")
    cur.execute("WITH n AS (SELECT TOP (100000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) n FROM sys.all_objects a CROSS JOIN sys.all_objects b) INSERT dbo.benchmark_shipments(customer_id, planned_departure_utc, status, shipped_qty) SELECT n % 1000, DATEADD(day, n % 365, '2026-01-01'), CASE WHEN n % 10 = 0 THEN 'Exception' ELSE 'Delivered' END, n % 500 FROM n")
    cur.execute("SET STATISTICS IO ON; SET STATISTICS TIME ON")
    for label, query in [("inefficient", "SELECT customer_id, SUM(shipped_qty) FROM dbo.benchmark_shipments WHERE CONVERT(date, planned_departure_utc) >= '2026-06-01' AND status = 'Exception' GROUP BY customer_id"), ("improved", "SELECT customer_id, SUM(shipped_qty) FROM dbo.benchmark_shipments WHERE planned_departure_utc >= '2026-06-01' AND status = 'Exception' GROUP BY customer_id")]:
        started = time.perf_counter(); rows = cur.execute(query).fetchall(); elapsed = time.perf_counter() - started
        print(label, "rows=", len(rows), "elapsed_seconds=", round(elapsed, 4))
    cur.execute("CREATE INDEX ix_benchmark_status_date ON dbo.benchmark_shipments(status, planned_departure_utc) INCLUDE (customer_id, shipped_qty)")
    print("Index created. Capture STATISTICS IO/TIME and an actual execution plan in SSMS or Query Store.")
