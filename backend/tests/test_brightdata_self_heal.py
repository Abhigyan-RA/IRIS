"""Tests for reading a page and repairing the attempt when the page has changed."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from shadow_cpi.ingestion.brightdata.self_heal import (
    FieldNameInstructionDrafter,
    SelfHealingPageRunner,
)
from shadow_cpi.shared import PipelineHealthEvent

PAGE = "<html><body>Copper 4.52 +1.8%</body></html>"

HEALTHY_ROWS: list[dict[str, object]] = [{"price": "4.52", "change_pct": "1.8"}]
EMPTY_ROWS: list[dict[str, object]] = []


class FakeFetcher:
    """Returns a page, or fails, as the test decides."""

    def __init__(self, page: str = PAGE, error: Exception | None = None, zone: bool = True) -> None:
        self.page = page
        self.error = error
        self.is_configured = zone
        self.fetched: list[str] = []

    async def fetch_page(self, url: str) -> str:
        self.fetched.append(url)
        if self.error is not None:
            raise self.error
        return self.page


class FakeReader:
    """Returns scripted rows, one script entry per attempt."""

    def __init__(self, attempts: Sequence[list[dict[str, object]]]) -> None:
        self._attempts = [list(rows) for rows in attempts]
        self.instructions: list[str | None] = []

    async def extract(
        self,
        html: str,
        description: str,
        entity_name: str,
        repair_instruction: str | None = None,
    ) -> list[dict[str, object]]:
        self.instructions.append(repair_instruction)
        return self._attempts.pop(0) if self._attempts else []


class RecordingEventWriter:
    def __init__(self) -> None:
        self.events: list[PipelineHealthEvent] = []

    async def record_event(self, event: PipelineHealthEvent) -> None:
        self.events.append(event)


def _runner(
    fetcher: FakeFetcher,
    reader: FakeReader,
    events: RecordingEventWriter,
    auto_approve: bool = True,
) -> SelfHealingPageRunner:
    return SelfHealingPageRunner(
        fetcher=fetcher,
        reader=reader,
        events=events,
        auto_approve_repairs=auto_approve,
    )


async def _run(runner: SelfHealingPageRunner) -> object:
    return await runner.run(
        collector_id="lme_copper_scraper",
        source_name="investing.com",
        url="https://www.investing.com/commodities/copper",
        description="the current copper price and its daily percent change",
        entity_name="Copper",
    )


def _types(events: RecordingEventWriter) -> list[str]:
    return [event.event_type.value for event in events.events]


class TestReadableePage:
    @pytest.mark.asyncio
    async def test_returns_the_values_read_from_the_page(self) -> None:
        events = RecordingEventWriter()

        outcome = await _run(_runner(FakeFetcher(), FakeReader([HEALTHY_ROWS]), events))

        assert outcome.rows == HEALTHY_ROWS  # type: ignore[attr-defined]
        assert outcome.healed is False  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_records_a_single_success(self) -> None:
        events = RecordingEventWriter()

        await _run(_runner(FakeFetcher(), FakeReader([HEALTHY_ROWS]), events))

        assert _types(events) == ["success"]

    @pytest.mark.asyncio
    async def test_reads_the_page_once_when_nothing_is_wrong(self) -> None:
        reader = FakeReader([HEALTHY_ROWS])

        await _run(_runner(FakeFetcher(), reader, RecordingEventWriter()))

        assert reader.instructions == [None]


class TestPageThatChanged:
    @pytest.mark.asyncio
    async def test_a_second_reading_with_guidance_recovers_the_values(self) -> None:
        events = RecordingEventWriter()
        reader = FakeReader([EMPTY_ROWS, HEALTHY_ROWS])

        outcome = await _run(_runner(FakeFetcher(), reader, events))

        assert outcome.rows == HEALTHY_ROWS  # type: ignore[attr-defined]
        assert outcome.healed is True  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_the_whole_sequence_is_written_to_the_health_feed(self) -> None:
        """This sequence is what proves the pipeline recovered without a person."""
        events = RecordingEventWriter()

        await _run(_runner(FakeFetcher(), FakeReader([EMPTY_ROWS, HEALTHY_ROWS]), events))

        assert _types(events) == [
            "dom_shift_detected",
            "self_heal_triggered",
            "self_heal_resolved",
        ]

    @pytest.mark.asyncio
    async def test_events_use_text_labels_rather_than_symbols(self) -> None:
        events = RecordingEventWriter()

        await _run(_runner(FakeFetcher(), FakeReader([EMPTY_ROWS, HEALTHY_ROWS]), events))

        messages = [event.message or "" for event in events.events]
        assert any("[WARNING]" in message for message in messages)
        assert any("[AUTO-HEALING]" in message for message in messages)
        assert any("[RESOLVED]" in message for message in messages)

    @pytest.mark.asyncio
    async def test_the_second_reading_is_given_guidance_naming_the_missing_value(self) -> None:
        reader = FakeReader([EMPTY_ROWS, HEALTHY_ROWS])

        await _run(_runner(FakeFetcher(), reader, RecordingEventWriter()))

        assert reader.instructions[0] is None
        assert "price" in (reader.instructions[1] or "")

    @pytest.mark.asyncio
    async def test_the_page_is_fetched_once_and_re_read_rather_than_re_fetched(self) -> None:
        """Re-fetching would cost another request for a page already in hand."""
        fetcher = FakeFetcher()

        await _run(_runner(fetcher, FakeReader([EMPTY_ROWS, HEALTHY_ROWS]), RecordingEventWriter()))

        assert len(fetcher.fetched) == 1

    @pytest.mark.asyncio
    async def test_a_repair_waits_for_a_person_when_that_is_configured(self) -> None:
        events = RecordingEventWriter()

        outcome = await _run(
            _runner(
                FakeFetcher(), FakeReader([EMPTY_ROWS, HEALTHY_ROWS]), events, auto_approve=False
            )
        )

        assert outcome.rows == []  # type: ignore[attr-defined]
        assert _types(events) == ["dom_shift_detected", "self_heal_triggered"]

    @pytest.mark.asyncio
    async def test_a_second_reading_that_still_finds_nothing_is_recorded_as_failed(self) -> None:
        events = RecordingEventWriter()

        outcome = await _run(_runner(FakeFetcher(), FakeReader([EMPTY_ROWS, EMPTY_ROWS]), events))

        assert outcome.rows == []  # type: ignore[attr-defined]
        assert _types(events)[-1] == "self_heal_failed"
        assert "price" in (events.events[-1].message or "")

    @pytest.mark.asyncio
    async def test_rows_missing_a_price_count_as_a_changed_page(self) -> None:
        events = RecordingEventWriter()
        reader = FakeReader([[{"price": None, "change_pct": "1.8"}], HEALTHY_ROWS])

        outcome = await _run(_runner(FakeFetcher(), reader, events))

        assert outcome.healed is True  # type: ignore[attr-defined]


class TestPageThatCannotBeFetched:
    @pytest.mark.asyncio
    async def test_a_fetch_failure_is_recorded_as_a_failed_collection(self) -> None:
        """Not a site redesign: the page was never seen, so the repair path is wrong here."""
        events = RecordingEventWriter()
        fetcher = FakeFetcher(error=RuntimeError("no zone configured"))

        outcome = await _run(_runner(fetcher, FakeReader([HEALTHY_ROWS]), events))

        assert outcome.rows == []  # type: ignore[attr-defined]
        assert _types(events) == ["collection_failed"]
        assert "no zone configured" in (events.events[0].message or "")

    @pytest.mark.asyncio
    async def test_a_fetch_failure_does_not_raise_into_the_run(self) -> None:
        outcome = await _run(
            _runner(
                FakeFetcher(error=RuntimeError("provider unavailable")),
                FakeReader([HEALTHY_ROWS]),
                RecordingEventWriter(),
            )
        )

        assert outcome.healed is False  # type: ignore[attr-defined]


class TestInstructionDrafter:
    @pytest.mark.asyncio
    async def test_describes_meaning_rather_than_position(self) -> None:
        instruction = await FieldNameInstructionDrafter().draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price",),
            reason="no rows returned",
        )

        assert "price" in instruction
        for word in ("css", "selector", "xpath", "nth"):
            assert word not in instruction.lower()

    @pytest.mark.asyncio
    async def test_stays_short_enough_to_be_useful(self) -> None:
        instruction = await FieldNameInstructionDrafter().draft(
            collector_id="lme_copper_scraper",
            missing_fields=("price", "change_pct"),
            reason="no rows returned",
        )

        assert 0 < len(instruction) <= 300
