"""Tests for the thin adapters that connect the repositories to real drivers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import TracebackType

import pytest

from shadow_cpi.db.neo4j.session import Neo4jSessionAdapter
from shadow_cpi.db.timescale.executor import PsycopgExecutor


class FakeCursor:
    """Stands in for a database cursor."""

    def __init__(self, rows: Sequence[Mapping[str, object]] = ()) -> None:
        self.executed: list[tuple[str, Sequence[object]]] = []
        self.batches: list[tuple[str, Sequence[Sequence[object]]]] = []
        self._rows = list(rows)

    async def execute(self, sql: str, params: Sequence[object] | None = None) -> None:
        self.executed.append((sql, params or ()))

    async def executemany(self, sql: str, param_sets: Sequence[Sequence[object]]) -> None:
        self.batches.append((sql, param_sets))

    async def fetchall(self) -> list[Mapping[str, object]]:
        return self._rows

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeConnection:
    """Stands in for a pooled database connection."""

    def __init__(self, rows: Sequence[Mapping[str, object]] = ()) -> None:
        self.cursors: list[FakeCursor] = []
        self.transactions = 0
        self._rows = list(rows)

    def cursor(self, *, row_factory: object = None) -> FakeCursor:
        self.row_factory = row_factory
        cursor = FakeCursor(self._rows)
        self.cursors.append(cursor)
        return cursor

    def transaction(self) -> FakeConnection:
        self.transactions += 1
        return self

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakePool:
    """Stands in for a connection pool."""

    def __init__(self, rows: Sequence[Mapping[str, object]] = ()) -> None:
        self.connection_calls = 0
        self.connections: list[FakeConnection] = []
        self._rows = list(rows)

    def connection(self) -> FakeConnection:
        self.connection_calls += 1
        connection = FakeConnection(self._rows)
        self.connections.append(connection)
        return connection


class TestPsycopgExecutor:
    @pytest.mark.asyncio
    async def test_execute_passes_sql_and_parameters_through(self) -> None:
        pool = FakePool()

        await PsycopgExecutor(pool).execute("SELECT 1 WHERE x = %s", ("value",))

        cursor = pool.connections[0].cursors[0]
        assert cursor.executed == [("SELECT 1 WHERE x = %s", ("value",))]

    @pytest.mark.asyncio
    async def test_execute_many_uses_one_round_trip(self) -> None:
        pool = FakePool()

        await PsycopgExecutor(pool).execute_many("INSERT INTO t VALUES (%s)", [(1,), (2,)])

        cursor = pool.connections[0].cursors[0]
        assert cursor.batches == [("INSERT INTO t VALUES (%s)", [(1,), (2,)])]
        assert pool.connection_calls == 1

    @pytest.mark.asyncio
    async def test_fetch_all_returns_rows_keyed_by_column_name(self) -> None:
        pool = FakePool([{"entity_name": "Copper"}])

        rows = await PsycopgExecutor(pool).fetch_all("SELECT entity_name FROM t")

        assert rows == [{"entity_name": "Copper"}]

    @pytest.mark.asyncio
    async def test_fetch_all_requests_dictionary_rows(self) -> None:
        """Repositories map rows by column name, so tuples would not work."""
        pool = FakePool([{"entity_name": "Copper"}])

        await PsycopgExecutor(pool).fetch_all("SELECT entity_name FROM t")

        assert pool.connections[0].row_factory is not None

    @pytest.mark.asyncio
    async def test_transaction_wraps_statements_in_one_unit_of_work(self) -> None:
        pool = FakePool()
        executor = PsycopgExecutor(pool)

        async with executor.transaction() as transaction:
            await transaction.execute("SELECT 1")

        assert pool.connections[0].transactions == 1

    @pytest.mark.asyncio
    async def test_statements_inside_a_transaction_share_one_connection(self) -> None:
        """Borrowing a second connection would place the work outside the transaction."""
        pool = FakePool([{"n": 1}])
        executor = PsycopgExecutor(pool)

        async with executor.transaction() as transaction:
            await transaction.execute("INSERT INTO t VALUES (%s)", (1,))
            await transaction.execute_many("INSERT INTO t VALUES (%s)", [(2,), (3,)])
            rows = await transaction.fetch_all("SELECT n FROM t")

        assert pool.connection_calls == 1
        assert rows == [{"n": 1}]
        cursors = pool.connections[0].cursors
        assert any(cursor.batches for cursor in cursors)


class FakeNeo4jResult:
    """Stands in for a Neo4j result cursor."""

    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self._rows = list(rows)

    async def data(self) -> list[Mapping[str, object]]:
        return self._rows


class FakeNeo4jSession:
    """Stands in for a Neo4j session."""

    def __init__(self, rows: Sequence[Mapping[str, object]] = ()) -> None:
        self.calls: list[tuple[str, Mapping[str, object]]] = []
        self._rows = list(rows)

    async def run(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
        **kwargs: object,
    ) -> FakeNeo4jResult:
        self.calls.append((query, dict(parameters or {})))
        return FakeNeo4jResult(self._rows)


class TestNeo4jSessionAdapter:
    @pytest.mark.asyncio
    async def test_returns_rows_as_plain_mappings(self) -> None:
        session = FakeNeo4jSession([{"target": "Stator Coil"}])

        rows = await Neo4jSessionAdapter(session).run("MATCH (n) RETURN n")

        assert rows == [{"target": "Stator Coil"}]

    @pytest.mark.asyncio
    async def test_parameters_are_forwarded_as_named_values(self) -> None:
        session = FakeNeo4jSession()

        await Neo4jSessionAdapter(session).run("MATCH (n {name: $name})", {"name": "Copper"})

        assert session.calls[0][1] == {"name": "Copper"}

    @pytest.mark.asyncio
    async def test_missing_parameters_are_allowed(self) -> None:
        session = FakeNeo4jSession()

        await Neo4jSessionAdapter(session).run("MATCH (n) RETURN count(n)")

        assert session.calls[0][1] == {}
