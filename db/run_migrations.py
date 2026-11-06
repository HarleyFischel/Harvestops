import os
from pathlib import Path

from harvestops.config import get_settings
from harvestops.repository import SqlServerRepository


def connect_for_migration():
    """Open a migration connection from an explicit string or application settings."""
    connection = os.environ.get("SQLSERVER_MIGRATION_CONNECTION")
    if connection:
        import pyodbc

        return pyodbc.connect(connection, autocommit=True)

    settings = get_settings()
    if settings.storage_mode != "sqlserver":
        raise SystemExit(
            "Set STORAGE_MODE=sqlserver and configure SQL_SERVER/SQL_DATABASE, "
            "or provide SQLSERVER_MIGRATION_CONNECTION"
        )
    errors = settings.validate_for_runtime()
    if errors:
        raise SystemExit("Invalid SQL migration configuration: " + "; ".join(errors))
    conn = SqlServerRepository(settings).connect()
    conn.autocommit = True
    return conn


def main():
    with connect_for_migration() as conn:
        for path in sorted(Path(__file__).parent.joinpath("migrations").glob("*.sql")):
            print(f"Applying {path.name}")
            conn.execute(path.read_text())
    print("Migrations complete")


if __name__ == "__main__":
    main()
