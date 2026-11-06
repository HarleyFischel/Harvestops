import sys
from types import SimpleNamespace

from db import run_migrations
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
