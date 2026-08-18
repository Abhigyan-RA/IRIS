"""Tests for the collection timetable."""

from __future__ import annotations

from collections.abc import Sequence

from shadow_cpi.orchestration.collector import CollectionOutcome
from shadow_cpi.orchestration.scheduler import CADENCES, build_scheduler


class StubService:
    """Records which sources were asked for, without collecting anything."""

    def __init__(self) -> None:
        self.requested: list[str] = []

    async def run_source(self, source_id: str) -> CollectionOutcome:
        self.requested.append(source_id)
        return CollectionOutcome(source_id=source_id, source_name="stub")


def _all_scheduled_sources() -> Sequence[str]:
    return [source_id for cadence in CADENCES for source_id in cadence.source_ids]


class TestCadences:
    def test_every_source_is_scheduled_exactly_once(self) -> None:
        """A source scheduled twice would be collected twice as often as intended."""
        scheduled = _all_scheduled_sources()

        assert len(scheduled) == len(set(scheduled))

    def test_every_shipped_source_appears_in_the_timetable(self) -> None:
        from shadow_cpi.ingestion.brightdata.collectors import SCRAPED_SOURCES

        scheduled = set(_all_scheduled_sources())
        expected = set(SCRAPED_SOURCES) | {
            "eia_petroleum_spot",
            "usda_grain_prices",
            "sec_edgar_13f",
        }

        assert expected <= scheduled, expected - scheduled

    def test_faster_moving_data_is_collected_more_often(self) -> None:
        by_name = {cadence.name: cadence.minutes for cadence in CADENCES}

        assert by_name["energy"] < by_name["freight"]
        assert by_name["freight"] < by_name["agriculture"]

    def test_no_source_is_polled_more_than_once_an_hour(self) -> None:
        """Polling faster than a source publishes spends money for identical answers."""
        assert all(cadence.minutes >= 60 for cadence in CADENCES)


class TestScheduler:
    def test_creates_one_job_per_group(self) -> None:
        scheduler = build_scheduler(StubService())  # type: ignore[arg-type]

        assert len(scheduler.get_jobs()) == len(CADENCES)

    def test_every_job_is_named_so_logs_are_readable(self) -> None:
        scheduler = build_scheduler(StubService())  # type: ignore[arg-type]

        for job in scheduler.get_jobs():
            assert job.name.startswith("Collect ")

    def test_a_slow_run_is_never_joined_by_a_second_copy(self) -> None:
        scheduler = build_scheduler(StubService())  # type: ignore[arg-type]

        for job in scheduler.get_jobs():
            assert job.max_instances == 1

    def test_missed_runs_collapse_into_one_rather_than_piling_up(self) -> None:
        """After a laptop wakes from sleep, a queue of identical runs is useless."""
        scheduler = build_scheduler(StubService())  # type: ignore[arg-type]

        for job in scheduler.get_jobs():
            assert job.coalesce is True
