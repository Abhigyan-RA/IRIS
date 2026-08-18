"""Connecting the pieces to real databases.

Everything else in this project depends on interfaces, which is what keeps it
testable. This module is where those interfaces are finally satisfied by real
drivers, so there is exactly one place to look for "what is connected to what".

It is deliberately thin: open connections, construct repositories, hand them over,
close the connections afterwards.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from shadow_cpi.ai.copilot import GroundedCopilot
from shadow_cpi.ai.explainer import GeminiRippleExplainer
from shadow_cpi.ai.gemini import GeminiClient
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import Settings
from shadow_cpi.db.neo4j.repository import Neo4jSupplyChainRepository
from shadow_cpi.db.neo4j.session import Neo4jSessionAdapter
from shadow_cpi.db.timescale.executor import ConnectionPool, PsycopgExecutor
from shadow_cpi.db.timescale.repositories import (
    TimescaleHealthEventRepository,
    TimescaleHoldingsRepository,
    TimescalePriceRepository,
)
from shadow_cpi.ingestion.http import HttpxClient


@asynccontextmanager
async def open_dependencies(  # pragma: no cover - requires live databases
    settings: Settings,
) -> AsyncIterator[ApiDependencies]:
    """Open every connection the application needs and build its dependencies.

    Args:
        settings: Configuration holding the connection details.

    Yields:
        A fully wired dependency container. Connections are closed when the block
        exits, including on error.
    """
    from neo4j import AsyncGraphDatabase
    from psycopg_pool import AsyncConnectionPool

    from shadow_cpi.ai.instruction_drafter import GeminiInstructionDrafter
    from shadow_cpi.ingestion.brightdata.studio import ScraperStudioClient
    from shadow_cpi.ingestion.brightdata.studio_runner import SelfHealingStudioRunner

    async with (
        AsyncConnectionPool(settings.database_url, open=False) as pool,
        HttpxClient() as http,
    ):
        await pool.open(wait=True)
        executor = PsycopgExecutor(cast("ConnectionPool", pool))

        model = GeminiClient(
            http=http,
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            daily_call_cap=settings.gemini_daily_call_cap,
        )

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
        try:
            async with driver.session() as session:
                health_events = TimescaleHealthEventRepository(executor)
                prices = TimescalePriceRepository(executor)
                holdings = TimescaleHoldingsRepository(executor)
                graph = Neo4jSupplyChainRepository(Neo4jSessionAdapter(session))
                yield ApiDependencies(
                    prices=prices,
                    holdings=holdings,
                    health_events=health_events,
                    graph=graph,
                    healer=SelfHealingStudioRunner(
                        api=ScraperStudioClient(
                            http=http,
                            api_key=settings.brightdata_api_key.get_secret_value(),
                        ),
                        events=health_events,
                        drafter=GeminiInstructionDrafter(model),
                        auto_approve_repairs=settings.brightdata_auto_approve_heal,
                    ),
                    copilot=GroundedCopilot(
                        model=model,
                        prices=prices,
                        holdings=holdings,
                        graph=graph,
                    ),
                    explainer=GeminiRippleExplainer(model),
                )
        finally:
            await driver.close()
