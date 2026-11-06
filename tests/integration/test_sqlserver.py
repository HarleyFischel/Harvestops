import os
import uuid
from datetime import date
from decimal import Decimal

import pytest

from harvestops.config import Settings
from harvestops.repository import SqlServerRepository
from harvestops.sql_store import SqlServerStore


def _configured_connection():
    direct = os.getenv("SQLSERVER_INTEGRATION_CONNECTION")
    if direct:
        return direct
    server = os.getenv("SQL_SERVER")
    database = os.getenv("SQL_DATABASE")
    user = os.getenv("SQL_USER")
    password = os.getenv("SQL_PASSWORD")
    if not all((server, database, user, password)) or password == "replace-me":
        return ""
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};DATABASE={database};UID={user};PWD={password};"
        "Encrypt=no;TrustServerCertificate=yes;"
    )


CONNECTION = _configured_connection()
pytestmark = pytest.mark.integration


def _sql_store():
    settings = Settings(
        storage_mode="sqlserver",
        sql_server="",
        sql_database="",
        sql_user="",
        sql_password="",
        sql_encrypt=False,
        sql_trust_server_certificate=True,
    )
    store = SqlServerStore(settings)
    store.repository.connection_string = lambda: CONNECTION
    return store


@pytest.mark.skipif(not CONNECTION, reason="SQLSERVER_INTEGRATION_CONNECTION is not configured")
def test_seeded_sql_server_exercises_tsql():
    class Settings:
        sql_server = ""
        sql_database = ""
        sql_user = ""
        sql_password = ""
        sql_auth_mode = "sql_login"
        sql_encrypt = False
        sql_trust_server_certificate = True
        sql_connection_timeout = 5

    repository = SqlServerRepository(Settings())
    repository.connection_string = lambda: CONNECTION
    assert repository.ping()
    rows = repository.shipment_rows({}, 1, 10)
    assert rows
    assert repository.shipment_count({}) >= len(rows)
    kpis = repository.shipment_kpis({})
    assert int(kpis["shipment_volume"]) >= 8
    aligned = repository.query(
        "SELECT shipment_id, actual_departure_utc FROM dbo.shipments "
        "WHERE shipment_id IN ('SHP-1002', 'SHP-1003') ORDER BY shipment_id"
    )
    assert len(aligned) == 2
    assert all(row["actual_departure_utc"] is not None for row in aligned)


@pytest.mark.skipif(not CONNECTION, reason="SQLSERVER_INTEGRATION_CONNECTION is not configured")
def test_sql_migrations_expose_staging_and_workflow_procedures():
    class Settings:
        sql_server = ""
        sql_database = ""
        sql_user = ""
        sql_password = ""
        sql_auth_mode = "sql_login"
        sql_encrypt = False
        sql_trust_server_certificate = True
        sql_connection_timeout = 5

    repository = SqlServerRepository(Settings())
    repository.connection_string = lambda: CONNECTION
    migration = repository.query("SELECT MAX(version) AS version FROM dbo.schema_migrations")[0]
    assert int(migration["version"]) >= 8
    staging = repository.query("SELECT OBJECT_ID('staging.shipment_updates', 'U') AS object_id")[0]
    workflow = repository.query(
        "SELECT OBJECT_ID('dbo.usp_change_shipment_status', 'P') AS object_id"
    )[0]
    importer = repository.query(
        "SELECT OBJECT_ID('dbo.usp_apply_shipment_import', 'P') AS object_id"
    )[0]
    labor = repository.query("SELECT OBJECT_ID('dbo.labor_records', 'U') AS object_id")[0]
    assert staging["object_id"] is not None
    assert workflow["object_id"] is not None
    assert importer["object_id"] is not None
    assert labor["object_id"] is not None


@pytest.mark.skipif(not CONNECTION, reason="SQLSERVER_INTEGRATION_CONNECTION is not configured")
def test_sql_import_status_change_and_audit_are_end_to_end():
    store = _sql_store()
    actor = store.users["demo.operator"]
    shipment_id = f"SHP-T{uuid.uuid4().hex[:10].upper()}"
    first = second = None
    csv_text = (
        "shipment_id,customer,product,facility,carrier,dock,planned_departure_utc,"
        "ordered_qty,shipped_qty,freight_cost,status\n"
        f"{shipment_id},City Market,Spring Mix,Salinas,GreenLine,D-07,"
        "2026-03-15T15:00:00Z,500,500,875,Scheduled\n"
    )
    first = store.import_shipments(csv_text, actor)
    second = store.import_shipments(csv_text, actor)
    try:
        assert first["applied"] == 1
        assert second["applied"] == 0
        shipment = store.get_shipment(shipment_id)
        assert shipment is not None
        updated = store.change_status(shipment_id, "In Transit", actor, shipment.version)
        assert updated.status == "In Transit"
        audit_rows = store.repository.query(
            "SELECT action_name FROM dbo.audit_events "
            "WHERE entity_id IN (?, ?) ORDER BY audit_event_id",
            (shipment_id, first["run_id"]),
        )
        assert {row["action_name"] for row in audit_rows} >= {
            "shipment.import",
            "shipment.status_changed",
        }
    finally:
        if first and second:
            first_run_id = int(first["run_id"].split("-")[1])
            second_run_id = int(second["run_id"].split("-")[1])
            with store.repository.connect() as conn:
                conn.execute(
                    "DELETE FROM dbo.audit_events WHERE entity_id IN (?, ?, ?)",
                    shipment_id,
                    first["run_id"],
                    second["run_id"],
                )
                conn.execute(
                    "DELETE FROM dbo.import_errors WHERE import_run_id IN (?, ?)",
                    first_run_id,
                    second_run_id,
                )
                conn.execute("DELETE FROM dbo.shipments WHERE shipment_id = ?", shipment_id)
                conn.execute(
                    "DELETE FROM dbo.import_runs WHERE import_run_id IN (?, ?)",
                    first_run_id,
                    second_run_id,
                )
                conn.commit()


@pytest.mark.skipif(not CONNECTION, reason="SQLSERVER_INTEGRATION_CONNECTION is not configured")
def test_sql_production_kpis_aggregate_labor_at_run_grain_and_apply_filters():
    store = _sql_store()
    repository = store.repository
    baseline_customer = repository.production_kpis(
        {
            "facility": "Salinas",
            "product": "Romaine Hearts",
            "customer": "FreshMart Northeast",
        }
    )
    run_ids: list[int] = []
    with repository.connect() as conn:
        facility_id = repository.rows(
            conn.execute(
                "SELECT facility_id FROM dbo.facilities WHERE facility_name = ?", "Salinas"
            )
        )[0]["facility_id"]
        product_id = repository.rows(
            conn.execute(
                "SELECT product_id FROM dbo.products WHERE product_name = ?", "Romaine Hearts"
            )
        )[0]["product_id"]
        for run_date, output_qty, labor_rows in (
            (date(2026, 4, 10), Decimal("100"), (Decimal("10"), Decimal("5"))),
            (date(2026, 4, 11), Decimal("200"), (Decimal("7"),)),
        ):
            run_id = int(
                conn.execute(
                    """INSERT dbo.production_runs(facility_id, product_id, run_date, output_qty, labor_hours)
                       OUTPUT INSERTED.production_run_id
                       VALUES (?, ?, ?, ?, ?)""",
                    facility_id,
                    product_id,
                    run_date,
                    output_qty,
                    Decimal("999"),
                ).fetchone()[0]
            )
            run_ids.append(run_id)
            for labor_hours in labor_rows:
                conn.execute(
                    """INSERT dbo.labor_records(production_run_id, work_date, labor_group, labor_hours)
                       VALUES (?, ?, ?, ?)""",
                    run_id,
                    run_date,
                    "Regression crew",
                    labor_hours,
                )
        conn.commit()

    try:
        bounded = repository.production_kpis(
            {
                "facility": "Salinas",
                "product": "Romaine Hearts",
                "start_date": "2026-04-10",
                "end_date": "2026-04-11",
            }
        )
        first_day = repository.production_kpis(
            {
                "facility": "Salinas",
                "product": "Romaine Hearts",
                "start_date": "2026-04-10",
                "end_date": "2026-04-10",
            }
        )
        customer_scoped = repository.production_kpis(
            {
                "facility": "Salinas",
                "product": "Romaine Hearts",
                "customer": "FreshMart Northeast",
            }
        )

        expected_bounded = {"production_output": Decimal("300"), "labor_hours": Decimal("22")}
        expected_first_day = {"production_output": Decimal("100"), "labor_hours": Decimal("15")}
        assert Decimal(bounded["production_output"]) == expected_bounded["production_output"]
        assert Decimal(bounded["labor_hours"]) == expected_bounded["labor_hours"]
        assert Decimal(first_day["production_output"]) == expected_first_day["production_output"]
        assert Decimal(first_day["labor_hours"]) == expected_first_day["labor_hours"]
        assert Decimal(customer_scoped["production_output"]) - Decimal(
            baseline_customer["production_output"]
        ) == Decimal("300.000")
        assert Decimal(customer_scoped["labor_hours"]) - Decimal(
            baseline_customer["labor_hours"]
        ) == Decimal("22.00")
    finally:
        with repository.connect() as conn:
            placeholders = ", ".join("?" for _ in run_ids)
            conn.execute(
                f"DELETE FROM dbo.labor_records WHERE production_run_id IN ({placeholders})",
                *run_ids,
            )
            conn.execute(
                f"DELETE FROM dbo.production_runs WHERE production_run_id IN ({placeholders})",
                *run_ids,
            )
            conn.commit()
