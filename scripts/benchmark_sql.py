"""Executable SQL performance case study; requires an external SQL Server."""

import os
import time

import pyodbc

CONNECTION = os.environ.get("SQLSERVER_MIGRATION_CONNECTION")
if not CONNECTION:
    raise SystemExit("Set SQLSERVER_MIGRATION_CONNECTION before running this benchmark")

with pyodbc.connect(CONNECTION, autocommit=True) as conn:
    cur = conn.cursor()
    print(
        "sql_version=",
        cur.execute("SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(40))").fetchone()[0],
    )
    cur.execute(
        "IF OBJECT_ID('dbo.benchmark_shipments','U') IS NOT NULL DROP TABLE dbo.benchmark_shipments; CREATE TABLE dbo.benchmark_shipments(id bigint IDENTITY PRIMARY KEY, customer_id int NOT NULL, planned_departure_utc datetime2 NOT NULL, status varchar(30) NOT NULL, shipped_qty int NOT NULL)"
    )
    cur.execute(
        "WITH n AS (SELECT TOP (100000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) n FROM sys.all_objects a CROSS JOIN sys.all_objects b) INSERT dbo.benchmark_shipments(customer_id, planned_departure_utc, status, shipped_qty) SELECT n % 1000, DATEADD(day, n % 365, '2026-01-01'), CASE WHEN n % 10 = 0 THEN 'Exception' ELSE 'Delivered' END, n % 500 FROM n"
    )
    print(
        "dataset_rows=", cur.execute("SELECT COUNT(*) FROM dbo.benchmark_shipments").fetchone()[0]
    )
    cur.execute("SET STATISTICS IO ON")
    cur.execute("SET STATISTICS TIME ON")

    queries = {
        "inefficient": "SELECT customer_id, SUM(shipped_qty) AS shipped_qty FROM dbo.benchmark_shipments WHERE CONVERT(date, planned_departure_utc) >= '2026-06-01' AND status = 'Exception' GROUP BY customer_id ORDER BY customer_id",
        "improved": "SELECT customer_id, SUM(shipped_qty) AS shipped_qty FROM dbo.benchmark_shipments WHERE planned_departure_utc >= '2026-06-01' AND status = 'Exception' GROUP BY customer_id ORDER BY customer_id",
    }
    results = {}
    for label, query in queries.items():
        started = time.perf_counter()
        results[label] = cur.execute(query).fetchall()
        elapsed = time.perf_counter() - started
        print(label, "rows=", len(results[label]), "elapsed_seconds=", round(elapsed, 4))
        if conn.messages:
            print(label, "sql_messages=", " | ".join(str(message[1]) for message in conn.messages))
            conn.messages.clear()

    if results["inefficient"] != results["improved"]:
        raise RuntimeError("inefficient and improved queries returned different results")
    print("matching_results= true")
    cur.execute(
        "CREATE INDEX ix_benchmark_status_date ON dbo.benchmark_shipments(status, planned_departure_utc) INCLUDE (customer_id, shipped_qty)"
    )
    started = time.perf_counter()
    indexed_rows = cur.execute(queries["improved"]).fetchall()
    elapsed = time.perf_counter() - started
    print("improved_indexed", "rows=", len(indexed_rows), "elapsed_seconds=", round(elapsed, 4))
    if indexed_rows != results["improved"]:
        raise RuntimeError("indexed query returned different results")
    if conn.messages:
        print(
            "improved_indexed sql_messages=",
            " | ".join(str(message[1]) for message in conn.messages),
        )
    print(
        "Index created. Capture the printed STATISTICS IO/TIME messages and an actual execution plan in SSMS or Query Store."
    )
