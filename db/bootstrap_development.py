"""Bootstrap the temporary local SQL Server profile without running the app as sa."""

import os
import re

from harvestops.config import Settings
from harvestops.repository import SqlServerRepository

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def quote_identifier(value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError("SQL identifiers may contain only letters, numbers, and underscores")
    return f"[{value}]"


def sql_literal(value: str) -> str:
    return "N'" + value.replace("'", "''") + "'"


def bootstrap() -> tuple[str, str]:
    server = os.environ.get("SQL_SERVER", "sqlserver,1433")
    database = os.environ.get("SQL_DATABASE", "HarvestOps")
    sa_user = os.environ.get("SQL_USER", "sa")
    sa_password = os.environ.get("SQL_PASSWORD") or os.environ.get("MSSQL_SA_PASSWORD", "")
    app_login = os.environ.get("HARVESTOPS_APP_LOGIN", "harvestops_app")
    app_password = os.environ.get("HARVESTOPS_APP_PASSWORD", "")
    quote_identifier(database)
    quote_identifier(app_login)
    if not sa_password or len(sa_password) < 8:
        raise SystemExit("MSSQL_SA_PASSWORD/SQL_PASSWORD must be at least 8 characters")
    if not app_password or len(app_password) < 8:
        raise SystemExit("HARVESTOPS_APP_PASSWORD must be at least 8 characters")

    settings = Settings(
        app_env="development",
        demo_mode=True,
        storage_mode="sqlserver",
        sql_server=server,
        sql_database="master",
        sql_auth_mode="sql_login",
        sql_user=sa_user,
        sql_password=sa_password,
        sql_encrypt=False,
        sql_trust_server_certificate=True,
    )
    repository = SqlServerRepository(settings)
    with repository.connect() as connection:
        connection.autocommit = True
        if connection.execute("SELECT DB_ID(?)", database).fetchone()[0] is None:
            connection.execute(f"CREATE DATABASE {quote_identifier(database)}")

        login_exists = connection.execute(
            "SELECT 1 FROM sys.server_principals WHERE name = ?", app_login
        ).fetchone()
        if not login_exists:
            connection.execute(
                f"CREATE LOGIN {quote_identifier(app_login)} WITH PASSWORD = {sql_literal(app_password)}, CHECK_POLICY = ON"
            )

        connection.execute(f"USE {quote_identifier(database)}")
        user_exists = connection.execute(
            "SELECT 1 FROM sys.database_principals WHERE name = ?", app_login
        ).fetchone()
        if not user_exists:
            connection.execute(
                f"CREATE USER {quote_identifier(app_login)} FOR LOGIN {quote_identifier(app_login)}"
            )

        for role in ("db_datareader", "db_datawriter"):
            role_member = connection.execute(
                """SELECT 1
                FROM sys.database_role_members drm
                JOIN sys.database_principals role_principal ON role_principal.principal_id = drm.role_principal_id
                JOIN sys.database_principals member_principal ON member_principal.principal_id = drm.member_principal_id
                WHERE role_principal.name = ? AND member_principal.name = ?""",
                role,
                app_login,
            ).fetchone()
            if not role_member:
                connection.execute(
                    f"ALTER ROLE {quote_identifier(role)} ADD MEMBER {quote_identifier(app_login)}"
                )
        connection.execute(f"GRANT EXECUTE ON SCHEMA::dbo TO {quote_identifier(app_login)}")
    print(f"SQL database ready: {database}; application login ready: {app_login}")
    return database, app_login


if __name__ == "__main__":
    bootstrap()
