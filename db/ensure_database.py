"""Create the configured SQL Server database when it does not exist."""

import os
import re

from harvestops.config import get_settings
from harvestops.repository import SqlServerRepository

_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def quote_database_name(name: str) -> str:
    if not isinstance(name, str) or not _DATABASE_NAME.fullmatch(name):
        raise ValueError("SQL database names may contain only letters, numbers, and underscores")
    return f"[{name}]"


def ensure_database() -> str:
    target = os.environ.get("HARVESTOPS_TARGET_DATABASE") or get_settings().sql_database
    quoted_target = quote_database_name(target)
    settings = get_settings().model_copy(update={"sql_database": "master"})
    errors = settings.validate_for_runtime()
    if errors:
        raise SystemExit("Invalid SQL bootstrap configuration: " + "; ".join(errors))

    repository = SqlServerRepository(settings)
    with repository.connect() as connection:
        connection.autocommit = True
        exists = connection.execute("SELECT DB_ID(?)", target).fetchone()[0]
        if exists is None:
            connection.execute(f"CREATE DATABASE {quoted_target}")
            print(f"Created SQL database {target}")
        else:
            print(f"SQL database {target} already exists")
    return target


if __name__ == "__main__":
    ensure_database()
