import os
from pathlib import Path

import pyodbc


def main():
    connection = os.environ.get("SQLSERVER_MIGRATION_CONNECTION")
    if not connection:
        raise SystemExit("Set SQLSERVER_MIGRATION_CONNECTION to an ODBC Driver 18 connection string")
    with pyodbc.connect(connection, autocommit=True) as conn:
        for path in sorted(Path(__file__).parent.joinpath("migrations").glob("*.sql")):
            print(f"Applying {path.name}")
            conn.execute(path.read_text())
    print("Migrations complete")


if __name__ == "__main__":
    main()
