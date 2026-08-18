"""Pipeline health endpoints, and the manual repair trigger.

These make the collection layer observable. The feed is the difference between
"this number looks old" and "this collector broke at 03:00, repaired itself at
03:02, and resumed at 03:03".

Two shapes are offered for the same data: a plain snapshot, which is simplest for a
page load, and a live stream for a dashboard that stays open. Both are polled from
the same store, so they can never disagree.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shadow_cpi.api.dependencies import (
    CollectorHealer,
    get_settings_from_request,
    require_cron_secret,
    require_healer,
    require_health_events,
)
from shadow_cpi.config import Settings
from shadow_cpi.db.protocols import HealthEventReader
from shadow_cpi.ingestion.brightdata.collectors import SCRAPED_SOURCES
from shadow_cpi.shared import PipelineHealthEvent

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500

# How often the live stream checks for new events, and how many times before it
# closes. A finite stream lets clients reconnect on their own terms and keeps
# connections from being held open forever by a forgotten browser tab.
_DEFAULT_INTERVAL_SECONDS = 2.0
_MAX_INTERVAL_SECONDS = 30.0
_DEFAULT_POLLS = 150
_MAX_POLLS = 10_000

router = APIRouter(prefix="/api", tags=["pipeline"])


class HealthEventOut(BaseModel):
    """One entry in the health feed.

    Attributes:
        scraper_id: Collector the entry concerns.
        source_name: Website it reads.
        event_type: Which stage of a run this represents.
        message: Human-readable detail, using text labels such as ``[WARNING]``.
        occurred_at: When it happened.
    """

    scraper_id: str
    source_name: str
    event_type: str
    message: str | None
    occurred_at: datetime


class HealthFeedResponse(BaseModel):
    """A snapshot of the feed.

    Attributes:
        events: Recent entries, newest first.
    """

    events: list[HealthEventOut]


class HealResponse(BaseModel):
    """The outcome of running a collector on demand.

    Attributes:
        collector_id: Collector that was run.
        source_name: Website it reads.
        healed: Whether a repair was needed and worked.
        rows_collected: How many rows came back.
        reason: Plain-language summary of the outcome.
    """

    collector_id: str
    source_name: str
    healed: bool
    rows_collected: int
    reason: str


def _to_out(event: PipelineHealthEvent) -> HealthEventOut:
    """Convert a stored event into its response shape.

    Args:
        event: The stored event.

    Returns:
        The entry as the feed renders it.
    """
    return HealthEventOut(
        scraper_id=event.scraper_id,
        source_name=event.source_name,
        event_type=event.event_type.value,
        message=event.message,
        occurred_at=event.occurred_at,
    )


@router.get(
    "/pipeline-health",
    response_model=HealthFeedResponse,
    summary="Recent collector activity",
)
async def read_health_feed(
    events: Annotated[HealthEventReader, Depends(require_health_events)],
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> HealthFeedResponse:
    """Return recent collector activity.

    Args:
        events: Event store to read from.
        limit: How many entries to return.

    Returns:
        The entries, newest first. A quiet pipeline returns an empty feed.
    """
    recent = await events.recent_events(limit=limit)
    return HealthFeedResponse(events=[_to_out(event) for event in recent])


async def _event_stream(
    events: HealthEventReader,
    polls: int,
    interval_seconds: float,
) -> AsyncIterator[str]:
    """Yield new events as they appear, in server-sent event format.

    Args:
        events: Event store to poll.
        polls: How many times to check before closing the stream.
        interval_seconds: How long to wait between checks.

    Yields:
        One server-sent event per new entry, and a comment line when there is
        nothing new. The comment keeps the connection alive: proxies and browsers
        close a stream that goes silent.
    """
    last_seen: datetime | None = None
    for poll_number in range(polls):
        recent = await events.recent_events(limit=_DEFAULT_LIMIT, since=last_seen)
        # Filter again here rather than trusting the store alone: two events can
        # share a timestamp, and a client must never see the same entry twice.
        fresh = [event for event in recent if last_seen is None or event.occurred_at > last_seen]
        if fresh:
            # The store returns newest first; the feed reads naturally oldest first.
            for event in reversed(fresh):
                yield f"data:{json.dumps(_to_out(event).model_dump(mode='json'))}\n\n"
            last_seen = max(event.occurred_at for event in fresh)
        elif poll_number == 0:
            yield ": no activity yet\n\n"
        if interval_seconds > 0:
            await asyncio.sleep(interval_seconds)


@router.get("/pipeline-health/stream", summary="Live collector activity")
async def stream_health_feed(
    events: Annotated[HealthEventReader, Depends(require_health_events)],
    polls: Annotated[int, Query(ge=1, le=_MAX_POLLS)] = _DEFAULT_POLLS,
    interval_seconds: Annotated[float, Query(ge=0, le=_MAX_INTERVAL_SECONDS)] = (
        _DEFAULT_INTERVAL_SECONDS
    ),
) -> StreamingResponse:
    """Stream collector activity as it happens.

    Args:
        events: Event store to poll.
        polls: How many times to check before closing the stream.
        interval_seconds: How long to wait between checks.

    Returns:
        A server-sent event stream. Caching is disabled explicitly, because a
        cached live feed would show a frozen pipeline.
    """
    return StreamingResponse(
        _event_stream(events, polls, interval_seconds),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            # Tells a reverse proxy not to buffer, which would delay every event
            # until the response was complete.
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/admin/scrapers/{collector_id}/heal",
    response_model=HealResponse,
    summary="Run one collector now, repairing it if needed",
    dependencies=[Depends(require_cron_secret)],
)
async def heal_collector(
    healer: Annotated[CollectorHealer, Depends(require_healer)],
    settings: Annotated[Settings, Depends(get_settings_from_request)],
    collector_id: Annotated[str, Path(min_length=1, max_length=100)],
) -> HealResponse:
    """Run a collector immediately and repair it if the page has changed.

    Protected by the shared secret, because it spends money at the scraping
    provider and sends traffic to a live website.

    Args:
        healer: Runner that drives the collector.
        settings: Active settings, which say which Scraper Studio collector belongs to
            this source.
        collector_id: Source to run, by its identifier in this project.

    Returns:
        What happened, reported honestly: a collector that could not be repaired
        returns zero rows rather than an error.

    Raises:
        HTTPException: If the collector is not one this platform knows about.
    """
    source = SCRAPED_SOURCES.get(collector_id)
    if source is None:
        known = ", ".join(sorted(SCRAPED_SOURCES))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown collector {collector_id!r}; known collectors: {known}",
        )

    collector = settings.collector_for(source.collector_id)
    if collector is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{collector_id} has no Scraper Studio collector yet. Build one with "
                f"bdata scraper create and add it to SCRAPER_STUDIO_COLLECTORS."
            ),
        )

    outcome = await healer.run(
        collector_id=collector,
        source_name=source.source_name,
        url=source.url,
    )
    return HealResponse(
        collector_id=source.collector_id,
        source_name=source.source_name,
        healed=outcome.healed,
        rows_collected=len(outcome.rows),
        reason=outcome.reason,
    )
