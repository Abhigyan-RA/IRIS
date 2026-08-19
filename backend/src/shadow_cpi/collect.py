"""Collect from the data sources now.

    python -m shadow_cpi.collect                  # every source
    python -m shadow_cpi.collect --source sec_edgar_13f
    python -m shadow_cpi.collect --list           # what is available, and what is ready

This is the command that fills the databases. The scheduler runs the same code on a
timetable; this exists so a person can run it deliberately, watch what happens, and see
why a source produced nothing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from shadow_cpi.config import Settings, get_settings
from shadow_cpi.db.timescale.executor import PsycopgExecutor
from shadow_cpi.db.timescale.repositories import (
    TimescaleHealthEventRepository,
    TimescaleHoldingsRepository,
    TimescalePriceRepository,
)
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.changes import HistoryChangeCalculator
from shadow_cpi.ingestion.http import HttpxClient
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.orchestration.collector import (
    CollectionOutcome,
    CollectionService,
    CollectionStores,
)
from shadow_cpi.runtime import bootstrap


def _register_sources() -> None:
    """Import the source packages, which is what registers them."""
    import shadow_cpi.ingestion.brightdata
    import shadow_cpi.ingestion.official  # noqa: F401


def _describe(outcome: CollectionOutcome) -> str:
    """Summarise one source's run in one line.

    Args:
        outcome: What the run achieved.

    Returns:
        A line to print.
    """
    if outcome.skipped:
        return f"SKIPPED  {outcome.source_id}: not configured, so nothing was requested"
    if outcome.error is not None:
        return f"FAILED   {outcome.source_id}: {outcome.error}"
    if outcome.records_written == 0:
        # Ran without error but stored nothing. Usually a repair that did not recover the
        # values, and the health feed says which. Reported distinctly so a run that
        # collected nothing does not read as a success.
        return f"EMPTY    {outcome.source_id}: ran, but no usable records were returned"
    return (
        f"OK       {outcome.source_id}: {outcome.prices_written} prices, "
        f"{outcome.holdings_written} holdings"
    )


async def _collect(  # pragma: no cover - needs live databases
    settings: Settings,
    source_id: str | None,
) -> int:
    """Run collection and store the results.

    Args:
        settings: Connection details and credentials.
        source_id: One source to run, or None for all of them.

    Returns:
        Process exit code: 0 unless every source that ran failed.
    """
    from psycopg_pool import AsyncConnectionPool

    from shadow_cpi.db.timescale.executor import ConnectionPool

    _register_sources()

    async with (
        AsyncConnectionPool(settings.database_url, open=False) as pool,
        HttpxClient() as http,
    ):
        await pool.open(wait=True)
        from typing import cast

        executor = PsycopgExecutor(cast("ConnectionPool", pool))
        institutional = TimescaleHoldingsRepository(executor)

        service = CollectionService(
            registry=default_registry,
            context=IngestionContext(
                http=http, settings=settings, events=TimescaleHealthEventRepository(executor)
            ),
            stores=CollectionStores(
                prices=TimescalePriceRepository(executor),
                holdings=institutional,
                events=TimescaleHealthEventRepository(executor),
                institutional=institutional,
            ),
            # Most pages publish a daily change and no weekly one, so the weekly figure is
            # worked out from the readings already stored.
            changes=HistoryChangeCalculator(TimescalePriceRepository(executor)),
        )

        outcomes = (
            [await service.run_source(source_id)]
            if source_id is not None
            else await service.run_all()
        )

    for outcome in outcomes:
        sys.stdout.write(f"{_describe(outcome)}\n")

    attempted = [outcome for outcome in outcomes if not outcome.skipped]
    stored = sum(outcome.records_written for outcome in outcomes)
    sys.stdout.write(f"\n{stored} records stored from {len(attempted)} sources that ran\n")

    if attempted and all(outcome.error is not None for outcome in attempted):
        return 1
    return 0


def _list_sources(settings: Settings) -> int:
    """Print the registered sources and whether each one can run.

    Args:
        settings: Credentials, which decide readiness.

    Returns:
        Process exit code.
    """
    _register_sources()
    context = IngestionContext(http=HttpxClient(), settings=settings)

    for source_id in default_registry.source_ids():
        ingestor = default_registry.build(source_id, context)
        ready = getattr(ingestor, "is_configured", True)
        state = "ready" if ready else "not configured"
        sys.stdout.write(f"{source_id:28} {getattr(ingestor, 'source_name', ''):28} {state}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m shadow_cpi.collect``.

    Args:
        argv: Command-line arguments. Defaults to those given to the process.

    Returns:
        Process exit code.
    """
    bootstrap()

    parser = argparse.ArgumentParser(description="Collect from the data sources now.")
    parser.add_argument("--source", help="run only this source, by identifier")
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the sources and whether each one is configured",
    )
    arguments = parser.parse_args(argv)

    settings = get_settings()
    if arguments.list:
        return _list_sources(settings)
    return asyncio.run(_collect(settings, arguments.source))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
