"""Applies pending database migrations.

The runner keeps a ``schema_migrations`` table listing the versions already
applied, so running it repeatedly is safe: it applies what is missing and nothing
else. Each migration runs inside its own transaction, so a failure leaves the
database on the last complete version rather than half-changed.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from shadow_cpi.db.protocols import Row, SqlExecutor
from shadow_cpi.db.timescale.migrations import Migration, load_migrations

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER     PRIMARY KEY,
    name        TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_SELECT_APPLIED = "SELECT version FROM schema_migrations ORDER BY version"

_RECORD_APPLIED = "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)"


class TransactionalExecutor(SqlExecutor, Protocol):
    """An executor that can also open a transaction.

    Written as a separate interface so that read-only callers are not forced to
    depend on transaction support they never use.
    """

    def transaction(self) -> AbstractAsyncContextManager[SqlExecutor]:
        """Open a transaction, yielding an executor bound to it."""
        ...


class Migrator:
    """Brings a database up to the latest schema version.

    Example:
        >>> from shadow_cpi.db.timescale.migrator import Migrator
        >>> applied = await Migrator(executor).upgrade()  # doctest: +SKIP
    """

    def __init__(
        self,
        executor: TransactionalExecutor,
        migrations: Sequence[Migration] | None = None,
    ) -> None:
        """Create a migrator.

        Args:
            executor: Database executor to run statements through. Passed in
                rather than constructed here, which is what lets tests substitute
                a recording fake.
            migrations: Migrations to consider. Defaults to those shipped with
                the package.
        """
        self._executor = executor
        self._migrations = list(migrations if migrations is not None else load_migrations())

    async def pending(self) -> list[Migration]:
        """Return the migrations that have not been applied yet.

        Useful for a startup check or a deployment log; it changes nothing.

        Returns:
            Pending migrations, oldest first.
        """
        await self._executor.execute(_CREATE_TRACKING_TABLE)
        rows: list[Row] = await self._executor.fetch_all(_SELECT_APPLIED)
        applied = {int(str(row["version"])) for row in rows}
        return [migration for migration in self._migrations if migration.version not in applied]

    async def upgrade(self) -> list[Migration]:
        """Apply every pending migration, oldest first.

        Returns:
            The migrations that were applied during this call. Empty when the
            database is already up to date.
        """
        pending = await self.pending()
        for migration in pending:
            async with self._executor.transaction() as transaction:
                await transaction.execute(migration.sql)
                await transaction.execute(_RECORD_APPLIED, (migration.version, migration.name))
        return pending
