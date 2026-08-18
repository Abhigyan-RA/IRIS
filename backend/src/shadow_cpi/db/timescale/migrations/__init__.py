"""Loads the SQL migration files that define the database schema.

Migrations are plain ``.sql`` files named ``NNN_description.sql``. The number is
the version and decides the order they run in. Plain SQL is used rather than a
migration framework so that the schema is readable by anyone who knows SQL, and
so it can be applied by hand in an emergency.

To add a migration, drop a new file in this directory with the next number. It is
picked up automatically; nothing else needs editing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIRECTORY = Path(__file__).resolve().parent

_FILENAME_PATTERN = re.compile(r"^(?P<version>\d+)_(?P<name>[a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    """One schema change.

    Attributes:
        version: Numeric version from the filename, used for ordering.
        name: Human-readable part of the filename.
        sql: Statements to run.
    """

    version: int
    name: str
    sql: str


def load_migrations(directory: Path | None = None) -> list[Migration]:
    """Read every migration in a directory, ordered by version.

    Ordering is numeric, not alphabetical: sorting filenames as text would put
    ``010_`` before ``002_`` and apply changes in the wrong order.

    Args:
        directory: Where to look. Defaults to the migrations shipped with the
            package.

    Returns:
        Migrations sorted from oldest to newest.

    Raises:
        ValueError: If a filename lacks a numeric prefix, two files share a
            version, or a file is empty.
    """
    root = directory or MIGRATIONS_DIRECTORY
    migrations: dict[int, Migration] = {}

    for path in sorted(root.glob("*.sql")):
        match = _FILENAME_PATTERN.match(path.name)
        if match is None:
            raise ValueError(
                f"Migration {path.name} must be named NNN_description.sql, "
                "for example 002_add_freight_lane_column.sql"
            )
        version = int(match.group("version"))
        if version in migrations:
            raise ValueError(
                f"Migration version {version} is duplicated by {path.name} and "
                f"{migrations[version].name}"
            )
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise ValueError(f"Migration {path.name} is empty")
        migrations[version] = Migration(version=version, name=match.group("name"), sql=sql)

    return [migrations[version] for version in sorted(migrations)]
