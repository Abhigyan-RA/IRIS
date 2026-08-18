"""Prepares both databases so the application has somewhere to write.

Run once after starting the databases, and again after pulling changes that add a
migration:

    python -m shadow_cpi.db.prepare

It applies any pending SQL migrations, creates the graph constraints, and loads
the starting graph. All three steps are safe to repeat.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, cast

from shadow_cpi.config import Settings, get_settings
from shadow_cpi.db.neo4j.repository import GraphSession, Neo4jSupplyChainRepository
from shadow_cpi.db.timescale.migrator import Migrator, TransactionalExecutor
from shadow_cpi.runtime import bootstrap

if TYPE_CHECKING:
    from shadow_cpi.db.timescale.executor import ConnectionPool


async def apply_database_schema(executor: TransactionalExecutor) -> list[str]:
    """Apply every pending SQL migration.

    Args:
        executor: Database executor to run the migrations through.

    Returns:
        Names of the migrations applied by this call, such as
        ``001_initial_schema``. Empty when the schema was already current.
    """
    applied = await Migrator(executor).upgrade()
    return [f"{migration.version:03d}_{migration.name}" for migration in applied]


async def prepare_graph(
    session: GraphSession,
    include_seed_data: bool = True,
) -> dict[str, int]:
    """Create the graph constraints and, by default, load the starting graph.

    Constraints come first: they are what make the seed's merges safe from
    creating duplicate nodes.

    Args:
        session: Graph session to run statements through.
        include_seed_data: Whether to load the starting nodes and relationships.
            Turn this off when pointing at a graph that already holds real data.

    Returns:
        How many nodes and relationships were written.
    """
    repository = Neo4jSupplyChainRepository(session)
    await repository.apply_constraints()
    if not include_seed_data:
        return {"nodes": 0, "edges": 0}
    return await repository.seed()


async def _run(settings: Settings) -> int:  # pragma: no cover - needs live databases
    """Connect to both databases and prepare them.

    Args:
        settings: Application settings holding the connection details.

    Returns:
        Process exit code.
    """
    from neo4j import AsyncGraphDatabase
    from psycopg_pool import AsyncConnectionPool

    from shadow_cpi.db.neo4j.session import Neo4jSessionAdapter
    from shadow_cpi.db.timescale.executor import PsycopgExecutor

    async with AsyncConnectionPool(settings.database_url, open=False) as pool:
        await pool.open(wait=True)
        # The pool satisfies the executor's expectations at runtime; the cast is
        # only needed because the driver's own signatures are wider than the small
        # interface this project depends on.
        executor = PsycopgExecutor(cast("ConnectionPool", pool))
        applied = await apply_database_schema(executor)
        if applied:
            sys.stdout.write(f"Applied migrations: {', '.join(applied)}\n")
        else:
            sys.stdout.write("Database schema already up to date\n")

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        async with driver.session() as session:
            summary = await prepare_graph(Neo4jSessionAdapter(session))
        sys.stdout.write(
            f"Graph ready: {summary['nodes']} nodes, {summary['edges']} relationships\n"
        )
    finally:
        await driver.close()

    return 0


def main() -> int:  # pragma: no cover - thin entry point around _run
    """Entry point for ``python -m shadow_cpi.db.prepare``.

    Returns:
        Process exit code.
    """
    bootstrap()
    return asyncio.run(_run(get_settings()))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
