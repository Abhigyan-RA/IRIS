"""Collecting on a timetable.

    python -m shadow_cpi.orchestration.scheduler

Each source is polled at roughly the rate it publishes. Polling faster than a source
updates costs money and quota for identical answers; polling slower than it updates loses
the early signal the product exists to provide.

Runs never overlap. A source that is slow or stuck must not accumulate copies of itself,
and two runs writing the same rows at once would compete for the same connection pool for
no benefit.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from shadow_cpi.config import Settings, get_settings
from shadow_cpi.orchestration.collector import CollectionService
from shadow_cpi.runtime import bootstrap


@dataclass(frozen=True, slots=True)
class Cadence:
    """How often one group of sources is collected.

    Attributes:
        name: What this group is called, used in logs.
        minutes: How many minutes between runs.
        source_ids: Sources in the group.
    """

    name: str
    minutes: int
    source_ids: tuple[str, ...]


# Rates follow how often each source actually publishes.
CADENCES: tuple[Cadence, ...] = (
    Cadence(
        name="energy",
        minutes=60,
        source_ids=("eia_petroleum_spot", "eia_wti_page", "eia_brent_page"),
    ),
    Cadence(
        name="metals and macro",
        minutes=120,
        source_ids=("lme_copper_scraper", "oilprice_scraper"),
    ),
    Cadence(
        name="freight",
        minutes=360,
        source_ids=("fbx_scraper", "baltic_dry_scraper"),
    ),
    Cadence(
        name="agriculture",
        minutes=1440,
        source_ids=("usda_grain_prices",),
    ),
    # Filings appear the moment the regulator posts them, and an hourly check is what
    # makes "same day as the filing" achievable without hammering a public service.
    Cadence(
        name="institutional filings",
        minutes=60,
        source_ids=("sec_edgar_13f",),
    ),
)


def build_scheduler(service: CollectionService) -> AsyncIOScheduler:
    """Create a scheduler with one job per group of sources.

    Args:
        service: Runs the sources and stores what they produce.

    Returns:
        A scheduler that has not been started yet.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    for cadence in CADENCES:

        async def collect(cadence: Cadence = cadence) -> None:
            """Run one group of sources.

            Args:
                cadence: The group to run, bound per job so each job keeps its own.
            """
            for source_id in cadence.source_ids:
                outcome = await service.run_source(source_id)
                if outcome.error is not None:
                    sys.stderr.write(f"[FAILED] {source_id}: {outcome.error}\n")

        scheduler.add_job(
            collect,
            trigger=IntervalTrigger(minutes=cadence.minutes),
            id=f"collect_{cadence.name.replace(' ', '_')}",
            name=f"Collect {cadence.name}",
            # A run that is still going when the next is due is left alone rather than
            # joined by a second copy of itself.
            max_instances=1,
            coalesce=True,
            # Collect once shortly after start, so a fresh deployment does not wait an
            # hour before it has anything to show.
            next_run_time=None,
        )

    return scheduler


async def _serve(settings: Settings) -> None:  # pragma: no cover - long-running process
    """Collect once, then keep collecting on the timetable.

    Args:
        settings: Connection details and credentials.
    """
    from typing import cast

    from psycopg_pool import AsyncConnectionPool

    from shadow_cpi.collect import _register_sources
    from shadow_cpi.db.timescale.executor import ConnectionPool, PsycopgExecutor
    from shadow_cpi.db.timescale.repositories import (
        TimescaleHealthEventRepository,
        TimescaleHoldingsRepository,
        TimescalePriceRepository,
    )
    from shadow_cpi.ingestion.base import IngestionContext
    from shadow_cpi.ingestion.http import HttpxClient
    from shadow_cpi.ingestion.registry import default_registry

    _register_sources()

    async with (
        AsyncConnectionPool(settings.database_url, open=False) as pool,
        HttpxClient() as http,
    ):
        await pool.open(wait=True)
        executor = PsycopgExecutor(cast("ConnectionPool", pool))
        service = CollectionService(
            registry=default_registry,
            context=IngestionContext(
                http=http, settings=settings, events=TimescaleHealthEventRepository(executor)
            ),
            prices=TimescalePriceRepository(executor),
            holdings=TimescaleHoldingsRepository(executor),
            events=TimescaleHealthEventRepository(executor),
        )

        sys.stdout.write("Collecting once before scheduling.\n")
        for outcome in await service.run_all():
            state = "SKIPPED" if outcome.skipped else "FAILED" if outcome.error else "OK"
            sys.stdout.write(f"{state:8} {outcome.source_id}\n")

        scheduler = build_scheduler(service)
        scheduler.start()
        for job in scheduler.get_jobs():
            sys.stdout.write(f"scheduled: {job.name}\n")
        sys.stdout.write("Running. Press Ctrl+C to stop.\n")

        # Sleep forever; the scheduler runs jobs on this loop.
        while True:
            await asyncio.sleep(3600)


def main() -> int:  # pragma: no cover - long-running process
    """Entry point for ``python -m shadow_cpi.orchestration.scheduler``.

    Returns:
        Process exit code.
    """
    bootstrap()
    try:
        asyncio.run(_serve(get_settings()))
    except KeyboardInterrupt:
        sys.stdout.write("Stopped.\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
