"""Running a Scraper Studio collector, and healing it when the target site changes.

This is the loop the product is built around, and it is worth being precise about what is
automated and what is not.

1. Run the collector. It returns the rows its own schema defines.
2. Inspect them. No rows, or rows whose price is missing, is what a redesigned page looks
   like from the outside: the scraper still runs, it just stops finding anything.
3. Describe what broke, in words. The model writes that description from the field names
   that stopped arriving, because a specific sentence produces a better fix than "it is
   broken".
4. Send it to Scraper Studio's self-healing, which rewrites the scraper's parsing code and
   returns a draft.
5. Approve the draft, unattended or after review, depending on configuration.
6. Run the collector again and check the rows.

The collector handle never changes through any of this, so schedules, the API, and the
dashboard all keep pointing at the same scraper. Every step is written to the health feed
with a text label, which is what makes the recovery visible after the fact rather than
something that has to be taken on trust.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol

from shadow_cpi.ingestion.brightdata.health import DEFAULT_REQUIRED_FIELDS, check_payload
from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome
from shadow_cpi.ingestion.brightdata.studio import HealStatus
from shadow_cpi.ingestion.repair import InstructionDrafter
from shadow_cpi.shared import PipelineEventType, PipelineHealthEvent

# One repair per run. A second attempt on the same run would cost another AI code change
# for a page that has already resisted one, and that is a job for a person.
_MAX_REPAIR_ATTEMPTS = 1


class StudioApi(Protocol):
    """The Scraper Studio operations this loop needs."""

    async def run(self, collector_id: str, url: str) -> list[Mapping[str, object]]:
        """Run a collector and return its rows."""
        ...

    async def heal(self, collector_id: str, prompt: str) -> HealStatus:
        """Ask for the collector to be repaired."""
        ...

    async def wait_for_heal(self, collector_id: str) -> HealStatus:
        """Wait for a repair to be drafted or applied."""
        ...

    async def approve_heal(self, collector_id: str, accept: bool = True) -> None:
        """Accept or discard a drafted repair."""
        ...


class HealthEventSink(Protocol):
    """Somewhere to record what happened during a run."""

    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Append one event."""
        ...


class SelfHealingStudioRunner:
    """Runs a collector and heals it in place when the target site changes."""

    def __init__(
        self,
        api: StudioApi,
        events: HealthEventSink,
        drafter: InstructionDrafter,
        auto_approve_repairs: bool,
        required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    ) -> None:
        """Create the runner.

        Args:
            api: Scraper Studio client.
            events: Where to record what happened.
            drafter: Writes the description of what broke that the repair is generated
                from.
            auto_approve_repairs: Whether to accept a drafted repair without review.
                Unattended recovery is what makes the pipeline survive a redesign
                overnight; requiring review is safer, because a repair could in principle
                capture the wrong number. A deployment choice, not a code one.
            required_fields: Fields a row must carry to count as usable.
        """
        self._api = api
        self._events = events
        self._drafter = drafter
        self._auto_approve = auto_approve_repairs
        self._required_fields = tuple(required_fields)

    async def run(  # noqa: PLR0911 - each exit reports a distinct, named outcome
        self,
        collector_id: str,
        source_name: str,
        url: str,
    ) -> RunOutcome:
        """Run a collector, healing it once if it stops finding the values.

        Args:
            collector_id: Collector to run.
            source_name: Website it reads, recorded with each event.
            url: Page to scrape.

        Returns:
            The rows collected, and whether a repair was needed to get them. A collector
            that cannot be made to work returns no rows rather than a guess.
        """
        try:
            rows = await self._api.run(collector_id, url)
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            await self._record(
                collector_id,
                source_name,
                PipelineEventType.COLLECTION_FAILED,
                f"[FAILED] could not run the collector: {reason}",
            )
            return RunOutcome(rows=[], healed=False, reason=reason)

        verdict = check_payload(rows, self._required_fields)
        if verdict.is_healthy:
            await self._record(
                collector_id, source_name, PipelineEventType.SUCCESS, f"[OK] {verdict.reason}"
            )
            return RunOutcome(rows=list(rows), healed=False, reason=verdict.reason)

        await self._record(
            collector_id,
            source_name,
            PipelineEventType.DOM_SHIFT_DETECTED,
            f"[WARNING] {source_name} changed: {verdict.reason}",
        )

        prompt = await self._drafter.draft(
            collector_id=collector_id,
            missing_fields=verdict.missing_fields,
            reason=verdict.reason,
        )
        status = await self._api.heal(collector_id, prompt)
        await self._record(
            collector_id,
            source_name,
            PipelineEventType.SELF_HEAL_TRIGGERED,
            f"[AUTO-HEALING] repair requested for: {', '.join(verdict.missing_fields)}",
        )

        # Live refactors begin as ``running`` while the code-fixer and preview runner work.
        # Treating that state as failure would make unattended repair fail at the exact moment
        # it was needed. Wait for a draft or an applied fix before deciding what to do.
        if status is HealStatus.RUNNING:
            status = await self._api.wait_for_heal(collector_id)

        if status is HealStatus.FAILED:
            return await self._fail(
                collector_id, source_name, "the repair could not be started", verdict.missing_fields
            )

        if status is HealStatus.AWAITING_APPROVAL:
            if not self._auto_approve:
                # Deliberately stops here. A fix exists but is unapproved, so nothing is
                # collected until a person accepts it.
                return RunOutcome(
                    rows=[], healed=False, reason="repair drafted and waiting for approval"
                )
            await self._api.approve_heal(collector_id)
            if await self._api.wait_for_heal(collector_id) is HealStatus.FAILED:
                return await self._fail(
                    collector_id,
                    source_name,
                    "the repair was not applied",
                    verdict.missing_fields,
                )

        for _ in range(_MAX_REPAIR_ATTEMPTS):
            try:
                retry_rows = await self._api.run(collector_id, url)
            except Exception as error:
                return await self._fail(
                    collector_id,
                    source_name,
                    f"{type(error).__name__} after repair",
                    verdict.missing_fields,
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

        return await self._fail(collector_id, source_name, verdict.reason, verdict.missing_fields)

    async def _fail(
        self,
        collector_id: str,
        source_name: str,
        reason: str,
        missing_fields: Sequence[str],
    ) -> RunOutcome:
        """Record that the repair did not work.

        Args:
            collector_id: Collector that stayed broken.
            source_name: Website it reads.
            reason: Why it is still unusable.
            missing_fields: Fields still not arriving.

        Returns:
            An empty outcome, so nothing wrong is stored.
        """
        fields = ", ".join(missing_fields) or "required fields"
        await self._record(
            collector_id,
            source_name,
            PipelineEventType.SELF_HEAL_FAILED,
            f"[FAILED] {fields} still missing after repair: {reason}",
        )
        return RunOutcome(rows=[], healed=False, reason=reason)

    async def _record(
        self,
        collector_id: str,
        source_name: str,
        event_type: PipelineEventType,
        message: str,
    ) -> None:
        """Append one event to the health feed.

        Args:
            collector_id: Collector the event concerns.
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
