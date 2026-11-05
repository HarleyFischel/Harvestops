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
