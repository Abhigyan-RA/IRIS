"""Tests for the migration runner and for the shipped migration files."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from shadow_cpi.db.timescale.migrations import MIGRATIONS_DIRECTORY, Migration, load_migrations
from shadow_cpi.db.timescale.migrator import Migrator


class FakeExecutor:
    """Records SQL instead of running it, so tests need no database."""

    def __init__(self, applied_versions: Sequence[int] = ()) -> None:
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self._applied = list(applied_versions)
        self.transactions = 0

    async def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        self.statements.append((sql, tuple(params)))

    async def fetch_all(
        self, sql: str, params: Sequence[object] = ()
    ) -> list[Mapping[str, object]]:
        self.statements.append((sql, tuple(params)))
        return [{"version": version} for version in self._applied]

    def transaction(self) -> FakeExecutor:
        self.transactions += 1
        return self

    async def __aenter__(self) -> FakeExecutor:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _sql_of(executor: FakeExecutor) -> str:
    return "\n".join(statement for statement, _ in executor.statements)


class TestLoadMigrations:
    def test_discovers_the_shipped_migrations(self) -> None:
        migrations = load_migrations()

        assert [migration.version for migration in migrations] == [1]
        assert migrations[0].name == "initial_schema"

    def test_orders_migrations_numerically_not_alphabetically(self, tmp_path: Path) -> None:
        for filename in ("010_tenth.sql", "002_second.sql", "001_first.sql"):
            (tmp_path / filename).write_text("SELECT 1;", encoding="utf-8")

        versions = [migration.version for migration in load_migrations(tmp_path)]

        assert versions == [1, 2, 10]

    def test_ignores_non_sql_files(self, tmp_path: Path) -> None:
        (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp_path / "notes.md").write_text("not a migration", encoding="utf-8")

        assert len(load_migrations(tmp_path)) == 1

    def test_rejects_a_filename_without_a_version_prefix(self, tmp_path: Path) -> None:
        (tmp_path / "add_column.sql").write_text("SELECT 1;", encoding="utf-8")

        with pytest.raises(ValueError, match="must be named"):
            load_migrations(tmp_path)

    def test_rejects_two_migrations_sharing_a_version(self, tmp_path: Path) -> None:
        (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
        (tmp_path / "001_also_first.sql").write_text("SELECT 2;", encoding="utf-8")

        with pytest.raises(ValueError, match="duplicate"):
            load_migrations(tmp_path)

    def test_rejects_an_empty_migration(self, tmp_path: Path) -> None:
        (tmp_path / "001_empty.sql").write_text("   \n", encoding="utf-8")

        with pytest.raises(ValueError, match="empty"):
            load_migrations(tmp_path)


class TestMigrator:
    @pytest.mark.asyncio
    async def test_creates_the_tracking_table_before_anything_else(self) -> None:
        executor = FakeExecutor()

        await Migrator(executor).upgrade()

        first_statement = executor.statements[0][0]
        assert "CREATE TABLE IF NOT EXISTS schema_migrations" in first_statement

    @pytest.mark.asyncio
    async def test_applies_pending_migrations_and_records_them(self) -> None:
        executor = FakeExecutor()

        applied = await Migrator(executor).upgrade()

        assert [migration.version for migration in applied] == [1]
        assert "CREATE TABLE IF NOT EXISTS commodity_prices" in _sql_of(executor)
        assert any(
            "INSERT INTO schema_migrations" in sql and params[0] == 1
            for sql, params in executor.statements
        )

    @pytest.mark.asyncio
    async def test_skips_migrations_that_are_already_applied(self) -> None:
        executor = FakeExecutor(applied_versions=[1])

        applied = await Migrator(executor).upgrade()

        assert applied == []
        assert "CREATE TABLE IF NOT EXISTS commodity_prices" not in _sql_of(executor)

    @pytest.mark.asyncio
    async def test_each_migration_runs_inside_a_transaction(self) -> None:
        """A half-applied schema change is worse than a failed one."""
        executor = FakeExecutor()

        await Migrator(executor).upgrade()

        assert executor.transactions == 1

    @pytest.mark.asyncio
    async def test_version_is_recorded_with_a_parameter_not_string_building(self) -> None:
        executor = FakeExecutor()

        await Migrator(executor).upgrade()

        insert = next(
            (sql, params)
            for sql, params in executor.statements
            if "INSERT INTO schema_migrations" in sql
        )
        assert "%s" in insert[0] or "$1" in insert[0]
        assert insert[1][0] == 1

    @pytest.mark.asyncio
    async def test_pending_migrations_can_be_inspected_without_applying(self) -> None:
        executor = FakeExecutor()

        pending = await Migrator(executor).pending()

        assert [migration.version for migration in pending] == [1]
        assert "CREATE TABLE IF NOT EXISTS commodity_prices" not in _sql_of(executor)

    @pytest.mark.asyncio
    async def test_uses_the_migrations_supplied_to_it(self, tmp_path: Path) -> None:
        (tmp_path / "001_custom.sql").write_text("CREATE TABLE demo (id INT);", encoding="utf-8")
        executor = FakeExecutor()

        await Migrator(executor, migrations=load_migrations(tmp_path)).upgrade()

        assert "CREATE TABLE demo" in _sql_of(executor)


class TestShippedSchema:
    """Checks on the SQL itself, so a bad edit fails before deployment."""

    @staticmethod
    def _initial_schema() -> str:
        return (MIGRATIONS_DIRECTORY / "001_initial_schema.sql").read_text(encoding="utf-8")

    def test_creates_the_three_tables(self) -> None:
        sql = self._initial_schema()

        for table in ("commodity_prices", "institutional_holdings", "pipeline_health_events"):
            assert f"CREATE TABLE IF NOT EXISTS {table}" in sql

    def test_every_table_becomes_a_hypertable(self) -> None:
        sql = self._initial_schema()

        assert sql.count("create_hypertable(") == 3
        assert "create_hypertable('commodity_prices', 'recorded_at'" in sql
        assert "create_hypertable('institutional_holdings', 'quarter_end'" in sql
        assert "create_hypertable('pipeline_health_events', 'occurred_at'" in sql

    def test_natural_keys_prevent_duplicate_rows(self) -> None:
        sql = self._initial_schema()

        assert "UNIQUE (entity_name, recorded_at)" in sql
        assert "UNIQUE (filer_cik, stock_ticker, quarter_end)" in sql

    def test_prices_record_where_they_came_from(self) -> None:
        sql = self._initial_schema()

        assert "source_url        TEXT          NOT NULL" in sql
        assert "ingestion_method" in sql

    def test_migration_is_safe_to_run_twice(self) -> None:
        """Every statement is written so a repeated run is a no-op."""
        sql = self._initial_schema()
        creating_lines = [
            line
            for line in sql.splitlines()
            if line.startswith(("CREATE TABLE", "CREATE INDEX", "CREATE EXTENSION"))
        ]

        assert creating_lines
        assert all("IF NOT EXISTS" in line for line in creating_lines)

    def test_migration_declares_a_migration_class_for_each_file(self) -> None:
        migrations = load_migrations()

        assert all(isinstance(migration, Migration) for migration in migrations)
        assert all(migration.sql.strip() for migration in migrations)
