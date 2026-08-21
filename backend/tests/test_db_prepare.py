"""Tests for the command that prepares both databases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from shadow_cpi.db.prepare import apply_database_schema, prepare_graph


class FakeExecutor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        self.statements.append(sql)

    async def fetch_all(
        self, sql: str, params: Sequence[object] = ()
    ) -> list[Mapping[str, object]]:
        self.statements.append(sql)
        return []

    def transaction(self) -> FakeExecutor:
        return self

    async def __aenter__(self) -> FakeExecutor:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def run(
        self, query: str, params: Mapping[str, object] | None = None
    ) -> list[Mapping[str, object]]:
        self.queries.append(query)
        return []


class TestApplyDatabaseSchema:
    @pytest.mark.asyncio
    async def test_reports_which_migrations_it_applied(self) -> None:
        executor = FakeExecutor()

        applied = await apply_database_schema(executor)

        assert applied == [
            "001_initial_schema",
            "002_institutional_enrichment",
            "003_holding_enrichment_sector",
        ]

    @pytest.mark.asyncio
    async def test_creates_the_price_table(self) -> None:
        executor = FakeExecutor()

        await apply_database_schema(executor)

        assert any("commodity_prices" in statement for statement in executor.statements)


class TestPrepareGraph:
    @pytest.mark.asyncio
    async def test_applies_constraints_before_writing_data(self) -> None:
        session = FakeSession()

        await prepare_graph(session)

        assert "CREATE CONSTRAINT" in session.queries[0]

    @pytest.mark.asyncio
    async def test_reports_how_much_seed_data_was_written(self) -> None:
        session = FakeSession()

        summary = await prepare_graph(session)

        assert summary["nodes"] > 0
        assert summary["edges"] > 0

    @pytest.mark.asyncio
    async def test_constraints_can_be_applied_without_seeding(self) -> None:
        """Useful against a graph that already holds real data."""
        session = FakeSession()

        summary = await prepare_graph(session, include_seed_data=False)

        assert summary == {"nodes": 0, "edges": 0}
        assert all("MERGE" not in query for query in session.queries)
