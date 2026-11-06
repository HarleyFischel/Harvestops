import sys
from types import SimpleNamespace

import pytest

from db import ensure_database, run_migrations
from db.ensure_database import quote_database_name
from harvestops.config import Settings
from harvestops.repository import SqlServerRepository


def test_sql_login_connection_string_is_parameterized_by_configuration():
    repository = SqlServerRepository(
        Settings(
            sql_server="sql.example,1433",
            sql_database="HarvestOps",
            sql_auth_mode="sql_login",
            sql_user="app_user",
            sql_password="secret-value",
            sql_encrypt=True,
            sql_trust_server_certificate=False,
        )
    )

    connection = repository.connection_string()
    assert "SERVER={sql.example,1433}" in connection
    assert "DATABASE={HarvestOps}" in connection
    assert "Encrypt=yes;TrustServerCertificate=no" in connection
    assert "UID={app_user};PWD={secret-value}" in connection


def test_sql_login_connection_string_quotes_punctuation_in_credentials():
    repository = SqlServerRepository(
        Settings(
            sql_server="sql.example,1433",
            sql_database="HarvestOps",
            sql_auth_mode="sql_login",
            sql_user="app;user",
            sql_password="p;word}",
        )
    )

    connection = repository.connection_string()
    assert "UID={app;user};" in connection
    assert "PWD={p;word}}};" in connection


def test_shipment_filter_parameterizes_dimensions_and_utc_date_scope():
    where, params = SqlServerRepository._shipment_filter(
        {
            "customer": "FreshMart Northeast",
            "product": "Romaine Hearts",
            "facility": "Salinas",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "exceptions_only": True,
        }
    )
    assert "customer_name = ?" in where
    assert "product_name = ?" in where
    assert "facility_name = ?" in where
    assert "planned_departure_utc >= CAST(? AS date)" in where
    assert "planned_departure_utc < DATEADD(day, 1, CAST(? AS date))" in where
    assert "status = ?" in where
    assert params == [
        "FreshMart Northeast",
        "Romaine Hearts",
        "Salinas",
        "2026-01-01",
        "2026-01-31",
        "Exception",
    ]


def test_database_bootstrap_only_accepts_safe_identifiers():
    assert quote_database_name("HarvestOps_2026") == "[HarvestOps_2026]"
    with pytest.raises(ValueError):
        quote_database_name("HarvestOps; DROP DATABASE master")


def test_database_bootstrap_creates_missing_database_on_master(monkeypatch):
    captured = {}

    class Result:
        def fetchone(self):
            return (None,)

    class Connection:
        autocommit = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, *params):
            captured.setdefault("statements", []).append((statement, params))
            return Result()

    class Repository:
        def __init__(self, settings):
            captured["database"] = settings.sql_database

        def connect(self):
            return Connection()

    monkeypatch.setenv("HARVESTOPS_TARGET_DATABASE", "HarvestOps")
    monkeypatch.setattr(
        ensure_database,
        "get_settings",
        lambda: Settings(
            storage_mode="sqlserver",
            sql_server="sql.example",
            sql_database="HarvestOps",
            sql_user="sa",
            sql_password="password",
            sql_encrypt=False,
            sql_trust_server_certificate=True,
        ),
    )
    monkeypatch.setattr(ensure_database, "SqlServerRepository", Repository)

    assert ensure_database.ensure_database() == "HarvestOps"
    assert captured["database"] == "master"
    assert captured["statements"][0] == ("SELECT DB_ID(?)", ("HarvestOps",))
    assert captured["statements"][1][0] == "CREATE DATABASE [HarvestOps]"


def test_azure_identity_connection_uses_sql_access_token(monkeypatch):
    captured = {}

    class Credential:
        def get_token(self, scope):
            captured["scope"] = scope
            return type("AccessToken", (), {"token": "token-value"})()

    def credential_factory(managed_identity_client_id=None):
        captured["client_id"] = managed_identity_client_id
        return Credential()

    monkeypatch.setattr("azure.identity.DefaultAzureCredential", credential_factory)

    def fake_connect(connection_string, attrs_before):
        captured["connection_string"] = connection_string
        captured["attrs_before"] = attrs_before
        return "connection"

    monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=fake_connect))
    repository = SqlServerRepository(
        Settings(
            sql_server="azure-sql.database.windows.net",
            sql_database="HarvestOps",
            sql_auth_mode="azure_identity",
            azure_client_id="managed-identity-client-id",
            sql_encrypt=True,
            sql_trust_server_certificate=False,
        )
    )

    assert repository.connect() == "connection"
    assert captured["client_id"] == "managed-identity-client-id"
    assert captured["scope"] == "https://database.windows.net/.default"
    assert "UID=" not in captured["connection_string"]
    assert 1256 in captured["attrs_before"]


def test_migration_connection_accepts_explicit_ci_connection(monkeypatch):
    captured = {}

    def fake_connect(connection, autocommit=False):
        captured.update(connection=connection, autocommit=autocommit)
        return object()

    monkeypatch.setenv(
        "SQLSERVER_MIGRATION_CONNECTION",
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=ci",
    )
    monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=fake_connect))
    assert run_migrations.connect_for_migration() is not None
    assert captured["connection"].endswith("SERVER=ci")
    assert captured["autocommit"] is True
