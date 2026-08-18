"""Reading a page, and repairing the attempt when the page has changed.

A page is read in two steps: fetch it through the scraping provider, then have the model
pick the values out of the text. Neither step involves a selector, so there is nothing to
break when a site is redesigned. What breaks instead is the model failing to find the
values, and that is recoverable by asking again with better guidance.

The loop:

1. Fetch the page and read the values.
2. Inspect what came back. Nothing, or rows with no price, means the page changed enough
   that the description no longer locates the values.
3. Write a sharper description of what to look for, from the page as it now reads.
4. Read it again with that guidance.
5. Record every step in the health feed, so the recovery is visible afterwards rather
   than invisible.

Each step is recorded with a text label such as ``[WARNING]``, ``[AUTO-HEALING]``, or
``[RESOLVED]``, which reads correctly in a terminal, in a log aggregator, and to a screen
reader alike.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from shadow_cpi.ingestion.brightdata.health import DEFAULT_REQUIRED_FIELDS, check_payload
from shadow_cpi.ingestion.repair import FieldNameInstructionDrafter, InstructionDrafter
from shadow_cpi.shared import PipelineEventType, PipelineHealthEvent

# One repair attempt per run. Asking repeatedly costs money at the provider and at the
# model for no better outcome, and a page that resists two readings needs a person.
_MAX_REPAIR_ATTEMPTS = 1


class PageFetcher(Protocol):
    """Fetches a page's content."""

    @property
    def is_configured(self) -> bool:
        """Whether pages can be fetched at all."""
        ...

    async def fetch_page(self, url: str) -> str:
        """Return the page content as text."""
        ...


class PageReader(Protocol):
    """Reads the requested values out of a page."""

    async def extract(
        self,
        html: str,
        description: str,
        entity_name: str,
        repair_instruction: str | None = None,
    ) -> list[dict[str, object]]:
        """Return one row per value found."""
        ...


class HealthEventSink(Protocol):
    """Somewhere to record what happened during a run."""

    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Append one event."""
        ...


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """What a run produced, after any repair.

    Attributes:
        rows: Usable rows, or empty when the page could not be read.
        healed: Whether a repair was needed and worked.
        reason: Plain-language summary of the final state.
    """

    rows: list[Mapping[str, object]]
    healed: bool
    reason: str


class SelfHealingPageRunner:
    """Reads a page, and repairs the attempt if the page has changed."""

    def __init__(  # noqa: PLR0913 - these are injected collaborators, not options
        self,
        fetcher: PageFetcher,
        reader: PageReader,
        events: HealthEventSink,
        auto_approve_repairs: bool,
        drafter: InstructionDrafter | None = None,
        required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    ) -> None:
        """Create the runner.

        Args:
            fetcher: Fetches the page through the scraping provider.
            reader: Reads values out of the page.
            events: Where to record what happened.
            auto_approve_repairs: Whether to apply a drafted repair without asking.
                Automatic recovery takes a minute with nobody watching; requiring
                approval is safer, because a repair could in principle pick the wrong
                number off the page. This is a deployment choice, not a code one.
            drafter: Writes the guidance for a second attempt. Defaults to the
                deterministic drafter, so the repair path never depends on a model.
            required_fields: Values a row must carry to count as usable.
        """
        self._fetcher = fetcher
        self._reader = reader
        self._events = events
        self._auto_approve = auto_approve_repairs
        self._drafter = drafter or FieldNameInstructionDrafter()
        self._required_fields = tuple(required_fields)

    async def run(
        self,
        collector_id: str,
        source_name: str,
        url: str,
        description: str,
        entity_name: str,
    ) -> RunOutcome:
        """Read a page, repairing the attempt once if it yields nothing usable.

        Args:
            collector_id: Source being read, recorded with each event.
            source_name: Website being read.
            url: Page to read.
            description: What to look for, in words.
            entity_name: What the value should be.

        Returns:
            The rows read, and whether a repair was needed to get them. A page that could
            not be read returns no rows rather than a guess.
        """
        try:
            html = await self._fetcher.fetch_page(url)
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            await self._record(
                collector_id,
                source_name,
                PipelineEventType.COLLECTION_FAILED,
                f"[FAILED] could not fetch {url}: {reason}",
            )
            return RunOutcome(rows=[], healed=False, reason=reason)

        rows = await self._reader.extract(html, description, entity_name)
        verdict = check_payload(rows, self._required_fields)

        if verdict.is_healthy:
            await self._record(
                collector_id,
                source_name,
                PipelineEventType.SUCCESS,
                f"[OK] {verdict.reason}",
            )
            return RunOutcome(rows=list(rows), healed=False, reason=verdict.reason)

        await self._record(
            collector_id,
            source_name,
            PipelineEventType.DOM_SHIFT_DETECTED,
            f"[WARNING] {source_name} reads differently: {verdict.reason}",
        )

        instruction = await self._drafter.draft(
            collector_id=collector_id,
            missing_fields=verdict.missing_fields,
            reason=verdict.reason,
        )
        await self._record(
            collector_id,
            source_name,
            PipelineEventType.SELF_HEAL_TRIGGERED,
            f"[AUTO-HEALING] re-reading the page for: {', '.join(verdict.missing_fields)}",
        )

        if not self._auto_approve:
            # Deliberately stops here. Guidance exists but is unapproved, so nothing is
            # collected until a person accepts it.
            return RunOutcome(
                rows=[],
                healed=False,
                reason="repair drafted and waiting for approval",
            )

        for _ in range(_MAX_REPAIR_ATTEMPTS):
            retry_rows = await self._reader.extract(
                html, description, entity_name, repair_instruction=instruction
            )
            retry_verdict = check_payload(retry_rows, self._required_fields)
            if retry_verdict.is_healthy:
                await self._record(
                    collector_id,
                    source_name,
                    PipelineEventType.SELF_HEAL_RESOLVED,
                    f"[RESOLVED] collection resumed: {retry_verdict.reason}",
                )
                return RunOutcome(rows=list(retry_rows), healed=True, reason=retry_verdict.reason)

        fields = ", ".join(verdict.missing_fields) or "required fields"
        await self._record(
            collector_id,
            source_name,
            PipelineEventType.SELF_HEAL_FAILED,
            f"[FAILED] {fields} still missing after re-reading: {verdict.reason}",
        )
        return RunOutcome(rows=[], healed=False, reason=verdict.reason)

    async def _record(
        self,
        collector_id: str,
        source_name: str,
        event_type: PipelineEventType,
        message: str,
    ) -> None:
        """Append one event to the health feed.

        Args:
            collector_id: Source the event concerns.
            source_name: Website it reads.
            event_type: Which stage this event represents.
            message: Human-readable detail.
        """
        await self._events.record_event(
            PipelineHealthEvent(
                scraper_id=collector_id,
                source_name=source_name,
                event_type=event_type,
                message=message,
                occurred_at=datetime.now(UTC),
            )
        )
