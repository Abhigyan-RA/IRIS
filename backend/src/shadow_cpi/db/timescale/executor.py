"""Connects the repositories to a real PostgreSQL/TimescaleDB server.

This module is the only place that knows which driver is in use. Everything else
depends on the executor interface, so swapping the driver, adding retries, or
logging slow queries happens here and nowhere else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from psycopg.rows import dict_row

from shadow_cpi.db.protocols import Row


class _Cursor(Protocol):
    """The part of a driver cursor this adapter uses."""

    async def execute(self, sql: str, params: Sequence[object] | None = None) -> object: ...

    async def executemany(self, sql: str, param_sets: Sequence[Sequence[object]]) -> object: ...

    async def fetchall(self) -> Sequence[Mapping[str, object]]: ...

    async def __aenter__(self) -> _Cursor: ...

    async def __aexit__(self, *args: object) -> object: ...


class _Connection(Protocol):
    """The part of a driver connection this adapter uses."""

    def cursor(self, *, row_factory: object = ...) -> _Cursor: ...

    def transaction(self) -> AbstractAsyncContextManager[object]: ...

    async def __aenter__(self) -> _Connection: ...

    async def __aexit__(self, *args: object) -> object: ...


class ConnectionPool(Protocol):
    """A pool that hands out connections.

    Declared as an interface rather than importing the concrete pool type so that
    tests can pass a fake, and so a different pool implementation can be dropped
    in without touching this file.
    """

    def connection(self) -> AbstractAsyncContextManager[_Connection]:
        """Borrow a connection for the duration of an ``async with`` block."""
        ...


class PsycopgExecutor:
    """Runs SQL against a pooled PostgreSQL connection.

    Every call borrows a connection, uses it, and returns it. Holding one open for
    the lifetime of the process would serialise all database work through a single
    connection and defeat the pool.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        """Create the executor.

        Args:
            pool: Connection pool to borrow from.
        """
        self._pool = pool

    async def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """Run a statement that returns no rows.

        Args:
            sql: Statement with ``%s`` placeholders.
            params: Values to bind to the placeholders.
        """
        async with self._pool.connection() as connection, connection.cursor() as cursor:
            await cursor.execute(sql, params)

    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[object]]) -> None:
        """Run one statement once per set of values, in a single round trip.

        Args:
            sql: Statement with ``%s`` placeholders.
            param_sets: One sequence of values per row to write.
        """
        async with self._pool.connection() as connection, connection.cursor() as cursor:
            await cursor.executemany(sql, param_sets)

    async def fetch_all(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        """Run a query and return all rows, keyed by column name.

        Args:
            sql: Query with ``%s`` placeholders.
            params: Values to bind to the placeholders.

        Returns:
            Rows as mappings of column name to value.
        """
        async with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PsycopgExecutor]:
        """Run several statements as one unit of work.

        Yields:
            An executor bound to a single connection inside a transaction. If the
            block raises, everything in it is rolled back.
        """
        async with self._pool.connection() as connection, connection.transaction():
            yield _SingleConnectionExecutor(connection)


class _SingleConnectionExecutor(PsycopgExecutor):
    """An executor pinned to one connection, used inside a transaction.

    Reusing the pool here would run statements on different connections, which
    would place them outside the transaction that was just opened.
    """

    def __init__(self, connection: _Connection) -> None:
        """Create the pinned executor.

        Args:
            connection: The connection already inside a transaction.
        """
        self._connection = connection

    async def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """Run a statement on the pinned connection.

        Args:
            sql: Statement with ``%s`` placeholders.
            params: Values to bind to the placeholders.
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute(sql, params)

    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[object]]) -> None:
        """Run one statement per set of values on the pinned connection.

        Args:
            sql: Statement with ``%s`` placeholders.
            param_sets: One sequence of values per row to write.
        """
        async with self._connection.cursor() as cursor:
            await cursor.executemany(sql, param_sets)

    async def fetch_all(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        """Run a query on the pinned connection.

        Args:
            sql: Query with ``%s`` placeholders.
            params: Values to bind to the placeholders.

        Returns:
            Rows as mappings of column name to value.
        """
        async with self._connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
