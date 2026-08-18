"""Tests for running and healing a Scraper Studio collector."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from shadow_cpi.ingestion.brightdata.studio import HealStatus
from shadow_cpi.ingestion.brightdata.studio_runner import SelfHealingStudioRunner
from shadow_cpi.shared import PipelineHealthEvent

COLLECTOR = "c_mswnopw72dyj64c7s3"
PAGE = "https://www.investing.com/commodities/copper"

HEALTHY_ROWS: list[Mapping[str, object]] = [
    {"price": {"value": 6.719, "currency": "USD"}, "price_change_percent": "(+1.65%)"}
]
EMPTY_ROWS: list[Mapping[str, object]] = []


class FakeStudio:
    """A Scraper Studio whose behaviour each test scripts."""

    def __init__(
        self,
        runs: Sequence[list[Mapping[str, object]]],
        heal_status: HealStatus = HealStatus.AWAITING_APPROVAL,
        wait_status: HealStatus = HealStatus.DONE,
        run_error: Exception | None = None,
    ) -> None:
        self._runs = [list(rows) for rows in runs]
        self._heal_status = heal_status
        self._wait_status = wait_status
        self._run_error = run_error
        self.run_calls: list[str] = []
        self.heal_prompts: list[str] = []
        self.approvals: list[bool] = []
        self.waits = 0

    async def run(self, collector_id: str, url: str) -> list[Mapping[str, object]]:
        self.run_calls.append(url)
        if self._run_error is not None:
            raise self._run_error
        return self._runs.pop(0) if self._runs else []

    async def heal(self, collector_id: str, prompt: str) -> HealStatus:
        self.heal_prompts.append(prompt)
        return self._heal_status

    async def wait_for_heal(self, collector_id: str) -> HealStatus:
        self.waits += 1
        return self._wait_status

    async def approve_heal(self, collector_id: str, accept: bool = True) -> None:
        self.approvals.append(accept)


class FixedDrafter:
    """Writes a predictable description of what broke."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], str]] = []

    async def draft(
        self,
        collector_id: str,
        missing_fields: Sequence[str],
        reason: str,
    ) -> str:
        self.calls.append((collector_id, tuple(missing_fields), reason))
        return f"The {', '.join(missing_fields)} field stopped arriving: {reason}"


class RecordingEventWriter:
    def __init__(self) -> None:
        self.events: list[PipelineHealthEvent] = []

    async def record_event(self, event: PipelineHealthEvent) -> None:
        self.events.append(event)


def _runner(
    studio: FakeStudio,
    events: RecordingEventWriter,
    auto_approve: bool = True,
    drafter: FixedDrafter | None = None,
) -> SelfHealingStudioRunner:
    return SelfHealingStudioRunner(
        api=studio,
        events=events,
        drafter=drafter or FixedDrafter(),
        auto_approve_repairs=auto_approve,
    )


def _types(events: RecordingEventWriter) -> list[str]:
    return [event.event_type.value for event in events.events]


class TestWorkingCollector:
    @pytest.mark.asyncio
    async def test_returns_the_rows_the_collector_produced(self) -> None:
        studio = FakeStudio([HEALTHY_ROWS])

        runner = _runner(studio, RecordingEventWriter())
        outcome = await runner.run(COLLECTOR, "investing.com", PAGE)

        assert outcome.rows == HEALTHY_ROWS
        assert outcome.healed is False

    @pytest.mark.asyncio
    async def test_records_a_single_success(self) -> None:
        events = RecordingEventWriter()

        runner = _runner(FakeStudio([HEALTHY_ROWS]), events)
        await runner.run(COLLECTOR, "investing.com", PAGE)

        assert _types(events) == ["success"]

    @pytest.mark.asyncio
    async def test_no_repair_is_requested_when_nothing_is_wrong(self) -> None:
        studio = FakeStudio([HEALTHY_ROWS])

        await _runner(studio, RecordingEventWriter()).run(COLLECTOR, "investing.com", PAGE)

        assert studio.heal_prompts == []
        assert studio.run_calls == [PAGE]


class TestSiteThatChanged:
    @pytest.mark.asyncio
    async def test_the_collector_is_healed_and_run_again(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, HEALTHY_ROWS])

        runner = _runner(studio, RecordingEventWriter())
        outcome = await runner.run(COLLECTOR, "investing.com", PAGE)

        assert outcome.rows == HEALTHY_ROWS
        assert outcome.healed is True
        assert len(studio.run_calls) == 2

    @pytest.mark.asyncio
    async def test_the_whole_sequence_is_written_to_the_health_feed(self) -> None:
        """This sequence is the evidence that the pipeline recovered on its own."""
        events = RecordingEventWriter()

        await _runner(FakeStudio([EMPTY_ROWS, HEALTHY_ROWS]), events).run(
            COLLECTOR, "investing.com", PAGE
        )

        assert _types(events) == [
            "dom_shift_detected",
            "self_heal_triggered",
            "self_heal_resolved",
        ]

    @pytest.mark.asyncio
    async def test_events_use_text_labels_rather_than_symbols(self) -> None:
        events = RecordingEventWriter()

        await _runner(FakeStudio([EMPTY_ROWS, HEALTHY_ROWS]), events).run(
            COLLECTOR, "investing.com", PAGE
        )

        messages = [event.message or "" for event in events.events]
        assert any("[WARNING]" in message for message in messages)
        assert any("[AUTO-HEALING]" in message for message in messages)
        assert any("[RESOLVED]" in message for message in messages)

    @pytest.mark.asyncio
    async def test_the_repair_prompt_names_the_field_that_stopped_arriving(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, HEALTHY_ROWS])
        drafter = FixedDrafter()

        await _runner(studio, RecordingEventWriter(), drafter=drafter).run(
            COLLECTOR, "investing.com", PAGE
        )

        assert "price" in studio.heal_prompts[0]
        assert drafter.calls[0][1] == ("price",)

    @pytest.mark.asyncio
    async def test_a_drafted_repair_is_approved_when_that_is_configured(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, HEALTHY_ROWS])

        await _runner(studio, RecordingEventWriter()).run(COLLECTOR, "investing.com", PAGE)

        assert studio.approvals == [True]
        assert studio.waits == 1

    @pytest.mark.asyncio
    async def test_a_repair_waits_for_a_person_when_that_is_configured(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, HEALTHY_ROWS])
        events = RecordingEventWriter()

        outcome = await _runner(studio, events, auto_approve=False).run(
            COLLECTOR, "investing.com", PAGE
        )

        assert outcome.rows == []
        assert studio.approvals == []
        assert _types(events) == ["dom_shift_detected", "self_heal_triggered"]

    @pytest.mark.asyncio
    async def test_a_repair_already_applied_is_not_approved_again(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, HEALTHY_ROWS], heal_status=HealStatus.DONE)

        await _runner(studio, RecordingEventWriter()).run(COLLECTOR, "investing.com", PAGE)

        assert studio.approvals == []

    @pytest.mark.asyncio
    async def test_a_repair_that_cannot_be_started_is_recorded_as_failed(self) -> None:
        studio = FakeStudio([EMPTY_ROWS], heal_status=HealStatus.FAILED)
        events = RecordingEventWriter()

        outcome = await _runner(studio, events).run(COLLECTOR, "investing.com", PAGE)

        assert outcome.rows == []
        assert _types(events)[-1] == "self_heal_failed"

    @pytest.mark.asyncio
    async def test_a_repair_that_is_never_applied_is_recorded_as_failed(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, HEALTHY_ROWS], wait_status=HealStatus.FAILED)
        events = RecordingEventWriter()

        outcome = await _runner(studio, events).run(COLLECTOR, "investing.com", PAGE)

        assert outcome.rows == []
        assert _types(events)[-1] == "self_heal_failed"

    @pytest.mark.asyncio
    async def test_a_run_still_empty_after_repair_is_recorded_as_failed(self) -> None:
        studio = FakeStudio([EMPTY_ROWS, EMPTY_ROWS])
        events = RecordingEventWriter()

        outcome = await _runner(studio, events).run(COLLECTOR, "investing.com", PAGE)

        assert outcome.rows == []
        assert "price" in (events.events[-1].message or "")

    @pytest.mark.asyncio
    async def test_rows_missing_a_price_count_as_a_changed_site(self) -> None:
        studio = FakeStudio([[{"price": None}], HEALTHY_ROWS])

        runner = _runner(studio, RecordingEventWriter())
        outcome = await runner.run(COLLECTOR, "investing.com", PAGE)

        assert outcome.healed is True


class TestCollectorThatCannotRun:
    @pytest.mark.asyncio
    async def test_a_run_failure_is_recorded_as_a_failed_collection(self) -> None:
        """Not a redesign: the collector never produced anything to judge."""
        studio = FakeStudio([], run_error=RuntimeError("returned status 404"))
        events = RecordingEventWriter()

        outcome = await _runner(studio, events).run(COLLECTOR, "investing.com", PAGE)

        assert outcome.rows == []
        assert _types(events) == ["collection_failed"]
        assert "404" in (events.events[0].message or "")

    @pytest.mark.asyncio
    async def test_a_failure_does_not_raise_into_the_run(self) -> None:
        studio = FakeStudio([], run_error=RuntimeError("provider unavailable"))

        runner = _runner(studio, RecordingEventWriter())
        outcome = await runner.run(COLLECTOR, "investing.com", PAGE)

        assert outcome.healed is False
