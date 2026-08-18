"""One-off check that the repositories work against real databases.

The test suite verifies behaviour against fakes at the driver boundary, which is what
keeps it fast and offline. That leaves one thing unproven: whether the SQL and Cypher
are actually accepted by TimescaleDB and Neo4j. This script answers that by writing and
reading real rows, then removing what it wrote.

Run it against local containers only. It is not part of the test suite because it needs
databases, and a suite that needs infrastructure is a suite people stop running.

    python -m shadow_cpi.db.smoke_check
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

from shadow_cpi.config import Settings, get_settings
from shadow_cpi.db.neo4j.repository import Neo4jSupplyChainRepository
from shadow_cpi.db.neo4j.session import Neo4jSessionAdapter
from shadow_cpi.db.timescale.executor import ConnectionPool, PsycopgExecutor
from shadow_cpi.db.timescale.repositories import (
    TimescaleHealthEventRepository,
    TimescaleHoldingsRepository,
    TimescalePriceRepository,
)
from shadow_cpi.runtime import bootstrap
from shadow_cpi.shared import (
    CommodityPrice,
    IngestionMethod,
    InstitutionalHolding,
    PipelineEventType,
    PipelineHealthEvent,
    Sector,
)

# Written and then deleted, so a real deployment is never left with test rows.
CHECK_ENTITY = "SmokeCheck_Metal"
CHECK_TICKER = "ZZZZ"
CHECK_CIK = "0009999999"
CHECK_SCRAPER = "smoke_check_scraper"

# Two prices are written, one day apart, which is the smallest history that can show
# ordering and a window query working.
EXPECTED_PRICE_ROWS = 2
EXPECTED_SHARES = 1_000


async def _check(settings: Settings) -> int:  # pragma: no cover - needs live databases
    """Write and read one row of each kind, then clean up.

    Args:
        settings: Connection details.

    Returns:
        Process exit code.
    """
    from neo4j import AsyncGraphDatabase
    from psycopg_pool import AsyncConnectionPool

    observed_at = datetime.now(UTC).replace(microsecond=0)

    async with AsyncConnectionPool(settings.database_url, open=False) as pool:
        await pool.open(wait=True)
        executor = PsycopgExecutor(cast("ConnectionPool", pool))

        prices = TimescalePriceRepository(executor)
        written = await prices.upsert_prices(
            [
                CommodityPrice(
                    entity_name=CHECK_ENTITY,
                    sector=Sector.METALS,
                    price=Decimal("4.5200"),
                    currency="USD",
                    unit="lb",
                    pct_change_1d=Decimal("1.800"),
                    recorded_at=observed_at,
                    source_name="smoke check",
                    source_url="https://example.invalid/smoke",
                    ingestion_method=IngestionMethod.OFFICIAL_API,
                ),
                CommodityPrice(
                    entity_name=CHECK_ENTITY,
                    sector=Sector.METALS,
                    price=Decimal("4.6000"),
                    currency="USD",
                    unit="lb",
                    recorded_at=observed_at - timedelta(days=1),
                    source_name="smoke check",
                    source_url="https://example.invalid/smoke",
                    ingestion_method=IngestionMethod.OFFICIAL_API,
                ),
            ]
        )
        latest = await prices.latest_price(CHECK_ENTITY)
        history = await prices.price_history(CHECK_ENTITY, days=7)
        by_sector = await prices.latest_prices_by_sector(Sector.METALS)
        # Writing the same natural key again must update rather than duplicate.
        await prices.upsert_prices(
            [
                CommodityPrice(
                    entity_name=CHECK_ENTITY,
                    sector=Sector.METALS,
                    price=Decimal("9.9900"),
                    currency="USD",
                    unit="lb",
                    recorded_at=observed_at,
                    source_name="smoke check",
                    source_url="https://example.invalid/smoke",
                    ingestion_method=IngestionMethod.OFFICIAL_API,
                )
            ]
        )
        after_upsert = await prices.latest_price(CHECK_ENTITY)

        holdings = TimescaleHoldingsRepository(executor)
        await holdings.upsert_holdings(
            [
                InstitutionalHolding(
                    filer_name="Smoke Check Capital",
                    filer_cik=CHECK_CIK,
                    stock_ticker=CHECK_TICKER,
                    shares_held=1_000,
                    market_value_usd=Decimal("12345.67"),
                    pct_portfolio=Decimal("1.500"),
                    shares_change_qoq=100,
                    quarter_end=observed_at.date(),
                    source_url="https://example.invalid/filing",
                )
            ]
        )
        holders = await holdings.holders_of(CHECK_TICKER)
        filer_rows = await holdings.holdings_of_filer(CHECK_CIK)

        events = TimescaleHealthEventRepository(executor)
        await events.record_event(
            PipelineHealthEvent(
                scraper_id=CHECK_SCRAPER,
                source_name="example.invalid",
                event_type=PipelineEventType.SELF_HEAL_RESOLVED,
                message="[RESOLVED] smoke check",
                occurred_at=observed_at,
            )
        )
        recent = await events.recent_events(limit=5)

        results = {
            "prices written": written == EXPECTED_PRICE_ROWS,
            "latest price read": latest is not None and latest.price == Decimal("4.5200"),
            "history read oldest first": len(history) == EXPECTED_PRICE_ROWS
            and history[0].recorded_at < history[1].recorded_at,
            "sector view returns one row per entity": any(
                row.entity_name == CHECK_ENTITY for row in by_sector
            ),
            "rerun updates instead of duplicating": after_upsert is not None
            and after_upsert.price == Decimal("9.9900"),
            "holding read back": len(holders) == 1 and holders[0].shares_held == EXPECTED_SHARES,
            "filer lookup normalizes its identifier": len(filer_rows) == 1,
            "event recorded": any(event.scraper_id == CHECK_SCRAPER for event in recent),
        }

        await _clean_up(executor, observed_at)

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        async with driver.session() as session:
            graph = Neo4jSupplyChainRepository(Neo4jSessionAdapter(session))
            links = await graph.ripple_effect("Copper", max_depth=2)
            exposure = await graph.filers_exposed_to("Copper")
        results["graph traversal returns a chain"] = len(links) > 0
        results["exposure query runs"] = isinstance(exposure, list)
    finally:
        await driver.close()

    for description, passed in results.items():
        sys.stdout.write(f"{'PASS' if passed else 'FAIL'}  {description}\n")
    return 0 if all(results.values()) else 1


async def _clean_up(
    executor: PsycopgExecutor,
    observed_at: datetime,
) -> None:  # pragma: no cover - needs live databases
    """Remove everything this check wrote.

    Args:
        executor: Database executor.
        observed_at: Timestamp the rows were written with.
    """
    await executor.execute("DELETE FROM commodity_prices WHERE entity_name = %s", (CHECK_ENTITY,))
    await executor.execute("DELETE FROM institutional_holdings WHERE filer_cik = %s", (CHECK_CIK,))
    await executor.execute(
        "DELETE FROM pipeline_health_events WHERE scraper_id = %s", (CHECK_SCRAPER,)
    )
    del observed_at


def main() -> int:  # pragma: no cover - thin entry point
    """Entry point for ``python -m shadow_cpi.db.smoke_check``.

    Returns:
        Process exit code.
    """
    bootstrap()
    return asyncio.run(_check(get_settings()))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
