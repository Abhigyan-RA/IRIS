"""Contract tests for the pipeline health feed and the manual repair trigger."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar

from fastapi.testclient import TestClient

from shadow_cpi.api.app import create_app
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome
from shadow_cpi.shared import PipelineEventType, PipelineHealthEvent

NOW = datetime(2026, 8, 15, 3, 0, tzinfo=UTC)

BASE_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
    "SCRAPER_STUDIO_COLLECTORS": "lme_copper_scraper=c_abc123",
}


def _event(
    event_type: PipelineEventType = PipelineEventType.SELF_HEAL_RESOLVED,
    message: str = "[RESOLVED] collection resumed",
    scraper_id: str = "whalewisdom_13f_scraper",
) -> PipelineHealthEvent:
    return PipelineHealthEvent(
        scraper_id=scraper_id,
        source_name="whalewisdom.com",
        event_type=event_type,
        message=message,
        occurred_at=NOW,
    )


class FakeHealthEventReader:
    """Serves canned events and records how it was queried."""

    def __init__(self, events: list[PipelineHealthEvent] | None = None) -> None:
        self._events = events or []
        self.calls: list[tuple[int, datetime | None]] = []

    async def recent_events(
        self, limit: int = 50, since: datetime | None = None
    ) -> list[PipelineHealthEvent]:
        self.calls.append((limit, since))
        return self._events


class FakeHealer:
    """Stands in for the self-healing runner."""

    def __init__(self, outcome: RunOutcome | None = None) -> None:
        self.outcome = outcome or RunOutcome(rows=[{"price": "4.52"}], healed=True, reason="fixed")
        self.calls: list[tuple[str, str, str]] = []

    async def run(self, collector_id: str, source_name: str, url: str) -> RunOutcome:
        self.calls.append((collector_id, source_name, url))
        return self.outcome


def _client(
    events: FakeHealthEventReader | None = None,
    healer: FakeHealer | None = None,
    **env: str,
) -> TestClient:
    app = create_app(
        build_settings({**BASE_ENV, **env}),
        dependencies=ApiDependencies(health_events=events, healer=healer),
    )
    return TestClient(app)


def _stream_events(body: str) -> list[dict[str, object]]:
    """Read the JSON payloads out of a server-sent event stream."""
    return [
        json.loads(line.removeprefix("data:").strip())
        for line in body.splitlines()
        if line.startswith("data:")
    ]


class TestHealthFeedSnapshot:
    def test_returns_recent_events_newest_first(self) -> None:
        client = _client(
            FakeHealthEventReader(
                [
                    _event(PipelineEventType.SELF_HEAL_RESOLVED),
                    _event(PipelineEventType.DOM_SHIFT_DETECTED, "[WARNING] layout changed"),
                ]
            )
        )

        body = client.get("/api/pipeline-health").json()

        assert [entry["event_type"] for entry in body["events"]] == [
            "self_heal_resolved",
            "dom_shift_detected",
        ]

    def test_each_event_carries_its_collector_source_and_message(self) -> None:
        client = _client(FakeHealthEventReader([_event()]))

        entry = client.get("/api/pipeline-health").json()["events"][0]

        assert entry["scraper_id"] == "whalewisdom_13f_scraper"
        assert entry["source_name"] == "whalewisdom.com"
        assert entry["message"] == "[RESOLVED] collection resumed"
        assert entry["occurred_at"].startswith("2026-08-15T03:00")

    def test_messages_use_text_labels_rather_than_symbols(self) -> None:
        client = _client(FakeHealthEventReader([_event(message="[AUTO-HEALING] repair requested")]))

        entry = client.get("/api/pipeline-health").json()["events"][0]

        assert "[AUTO-HEALING]" in entry["message"]

    def test_the_number_of_events_can_be_chosen(self) -> None:
        events = FakeHealthEventReader([_event()])
        client = _client(events)

        client.get("/api/pipeline-health", params={"limit": 10})

        assert events.calls == [(10, None)]

    def test_an_excessive_limit_is_refused(self) -> None:
        events = FakeHealthEventReader()
        client = _client(events)

        response = client.get("/api/pipeline-health", params={"limit": 10_000})

        assert response.status_code == 422
        assert events.calls == []

    def test_a_quiet_pipeline_returns_an_empty_feed(self) -> None:
        response = _client(FakeHealthEventReader()).get("/api/pipeline-health")

        assert response.status_code == 200
        assert response.json()["events"] == []

    def test_the_feed_reports_unavailability_when_no_store_is_configured(self) -> None:
        response = _client().get("/api/pipeline-health")

        assert response.status_code == 503


class TestHealthFeedStream:
    # Every stream test passes an explicit, tiny window. The production defaults
    # keep a connection open for minutes, which a test must never wait for.
    STREAM_PARAMS: ClassVar[dict[str, object]] = {"polls": 1, "interval_seconds": 0}

    def test_streams_events_as_server_sent_events(self) -> None:
        client = _client(FakeHealthEventReader([_event()]))

        with client.stream(
            "GET", "/api/pipeline-health/stream", params=self.STREAM_PARAMS
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())

        payloads = _stream_events(body)
        assert payloads[0]["event_type"] == "self_heal_resolved"

    def test_the_stream_is_never_cached_by_a_proxy(self) -> None:
        """A cached live feed would show a frozen pipeline."""
        client = _client(FakeHealthEventReader([_event()]))

        with client.stream(
            "GET", "/api/pipeline-health/stream", params=self.STREAM_PARAMS
        ) as response:
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-accel-buffering"] == "no"
            "".join(response.iter_text())

    def test_the_stream_ends_after_the_requested_number_of_polls(self) -> None:
        events = FakeHealthEventReader([_event()])
        client = _client(events)

        with client.stream(
            "GET", "/api/pipeline-health/stream", params={"polls": 2, "interval_seconds": 0}
        ) as response:
            "".join(response.iter_text())

        assert len(events.calls) == 2

    def test_events_already_sent_are_not_repeated(self) -> None:
        events = FakeHealthEventReader([_event()])
        client = _client(events)

        with client.stream(
            "GET", "/api/pipeline-health/stream", params={"polls": 3, "interval_seconds": 0}
        ) as response:
            body = "".join(response.iter_text())

        assert len(_stream_events(body)) == 1

    def test_a_quiet_stream_sends_a_keepalive_comment(self) -> None:
        """Without traffic, proxies and browsers close an idle connection."""
        client = _client(FakeHealthEventReader())

        with client.stream(
            "GET", "/api/pipeline-health/stream", params={"polls": 1, "interval_seconds": 0}
        ) as response:
            body = "".join(response.iter_text())

        assert body.startswith(":")


class TestManualRepairTrigger:
    def test_triggering_a_repair_reports_the_outcome(self) -> None:
        healer = FakeHealer()
        client = _client(healer=healer)

        response = client.post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "test-cron-secret"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["collector_id"] == "lme_copper_scraper"
        assert body["healed"] is True
        assert body["rows_collected"] == 1

    def test_the_named_collector_is_the_one_that_runs(self) -> None:
        healer = FakeHealer()
        client = _client(healer=healer)

        client.post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "test-cron-secret"},
        )

        assert healer.calls == [
            ("c_abc123", "investing.com", "https://www.investing.com/commodities/copper")
        ]

    def test_an_unknown_collector_is_refused(self) -> None:
        healer = FakeHealer()
        client = _client(healer=healer)

        response = client.post(
            "/api/admin/scrapers/not-a-collector/heal",
            headers={"X-Cron-Secret": "test-cron-secret"},
        )

        assert response.status_code == 404
        assert healer.calls == []

    def test_the_endpoint_requires_the_shared_secret(self) -> None:
        """This endpoint spends money and touches a live site, so it is not public."""
        healer = FakeHealer()
        client = _client(healer=healer)

        response = client.post("/api/admin/scrapers/lme_copper_scraper/heal")

        assert response.status_code == 401
        assert healer.calls == []

    def test_a_wrong_secret_is_refused(self) -> None:
        healer = FakeHealer()
        client = _client(healer=healer)

        response = client.post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "wrong"},
        )

        assert response.status_code == 401
        assert healer.calls == []

    def test_the_error_never_echoes_the_expected_secret(self) -> None:
        client = _client(healer=FakeHealer())

        response = client.post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "wrong"},
        )

        assert "test-cron-secret" not in response.text

    def test_a_collector_that_could_not_be_repaired_is_reported_honestly(self) -> None:
        healer = FakeHealer(RunOutcome(rows=[], healed=False, reason="still broken"))
        client = _client(healer=healer)

        body = client.post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "test-cron-secret"},
        ).json()

        assert body["healed"] is False
        assert body["rows_collected"] == 0
        assert body["reason"] == "still broken"

    def test_a_source_without_a_collector_is_reported_as_a_conflict(self) -> None:
        """Nothing can be healed until a Scraper Studio collector has been built for it."""
        healer = FakeHealer()
        client = _client(healer=healer, SCRAPER_STUDIO_COLLECTORS="")

        response = client.post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "test-cron-secret"},
        )

        assert response.status_code == 409
        assert "bdata scraper create" in response.json()["detail"]
        assert healer.calls == []

    def test_the_endpoint_reports_unavailability_when_no_runner_is_configured(self) -> None:
        response = _client().post(
            "/api/admin/scrapers/lme_copper_scraper/heal",
            headers={"X-Cron-Secret": "test-cron-secret"},
        )

        assert response.status_code == 503
