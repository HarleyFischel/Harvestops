import os

import pytest

from harvestops.repository import SqlServerRepository

CONNECTION = os.getenv("SQLSERVER_INTEGRATION_CONNECTION")
pytestmark = pytest.mark.integration


@pytest.mark.skipif(not CONNECTION, reason="SQLSERVER_INTEGRATION_CONNECTION is not configured")
def test_seeded_sql_server_exercises_tsql():
    class Settings:
        sql_server = ""
        sql_database = ""
        sql_user = ""
        sql_password = ""
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
        sql_encrypt = False
        sql_trust_server_certificate = True
        sql_connection_timeout = 5

    repository = SqlServerRepository(Settings())
    repository.connection_string = lambda: CONNECTION
    migration = repository.query("SELECT MAX(version) AS version FROM dbo.schema_migrations")[0]
    assert int(migration["version"]) >= 7
    staging = repository.query("SELECT OBJECT_ID('staging.shipment_updates', 'U') AS object_id")[0]
    workflow = repository.query(
        "SELECT OBJECT_ID('dbo.usp_change_shipment_status', 'P') AS object_id"
    )[0]
    importer = repository.query(
        "SELECT OBJECT_ID('dbo.usp_apply_shipment_import', 'P') AS object_id"
    )[0]
    assert staging["object_id"] is not None
    assert workflow["object_id"] is not None
    assert importer["object_id"] is not None
