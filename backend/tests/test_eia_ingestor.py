"""Tests for the EIA petroleum spot-price ingestor."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.official.eia import (
    EIA_SERIES,
    EiaPetroleumSpotIngestor,
)
from shadow_cpi.shared import IngestionMethod, Sector

BASE_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
}


class FakeHttpClient:
    """Returns a canned payload and records how it was called."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[tuple[str, Mapping[str, str | int], Mapping[str, str]]] = []

    async def get_json(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        return self.payload

    async def get_text(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        raise AssertionError("this source reads JSON only")


def _payload(*observations: Mapping[str, Any]) -> dict[str, Any]:
    return {"response": {"total": len(observations), "data": list(observations)}}


def _observation(
    series: str = "RWTC",
    period: str = "2026-08-14",
    value: float | None = 78.21,
    units: str = "$/BBL",
) -> dict[str, Any]:
    return {"series": series, "period": period, "value": value, "units": units}


def _context(payload: object, **env: str) -> tuple[IngestionContext, FakeHttpClient]:
    client = FakeHttpClient(payload)
    settings = build_settings({**BASE_ENV, **env})
    return IngestionContext(http=client, settings=settings), client


class TestConfiguration:
    def test_source_is_identified_for_schedules_and_logs(self) -> None:
        context, _ = _context(_payload(), EIA_API_KEY="test-eia-key")

        ingestor = EiaPetroleumSpotIngestor(context)

        assert ingestor.source_id == "eia_petroleum_spot"
        assert ingestor.source_name == "eia.gov"

    def test_reports_itself_configured_when_a_key_is_present(self) -> None:
        context, _ = _context(_payload(), EIA_API_KEY="test-eia-key")

        assert EiaPetroleumSpotIngestor(context).is_configured is True

    def test_reports_itself_unconfigured_without_a_key(self) -> None:
        """The key is optional, so a run must skip this source rather than crash."""
        context, _ = _context(_payload())

        assert EiaPetroleumSpotIngestor(context).is_configured is False

    @pytest.mark.asyncio
    async def test_ingesting_without_a_key_returns_nothing_and_makes_no_request(self) -> None:
        context, client = _context(_payload(_observation()))

        result = await EiaPetroleumSpotIngestor(context).ingest()

        assert result.record_count == 0
        assert client.calls == []

    def test_tracked_series_cover_the_headline_crude_benchmarks(self) -> None:
        assert EIA_SERIES["RWTC"].entity_name == "WTI_Crude"
        assert EIA_SERIES["RBRTE"].entity_name == "Brent_Crude"
        assert all(series.unit == "barrel" for series in EIA_SERIES.values())


class TestHealthyPayload:
    @pytest.mark.asyncio
    async def test_maps_an_observation_to_a_price_record(self) -> None:
        context, _ = _context(_payload(_observation()), EIA_API_KEY="test-eia-key")

        result = await EiaPetroleumSpotIngestor(context).ingest()

        price = result.prices[0]
        assert price.entity_name == "WTI_Crude"
        assert price.sector is Sector.ENERGY
        assert price.price == Decimal("78.21")
        assert price.currency == "USD"
        assert price.unit == "barrel"
        assert price.ingestion_method is IngestionMethod.OFFICIAL_API

    @pytest.mark.asyncio
    async def test_records_the_endpoint_it_read_from(self) -> None:
        context, _ = _context(_payload(_observation()), EIA_API_KEY="test-eia-key")

        result = await EiaPetroleumSpotIngestor(context).ingest()

        assert result.prices[0].source_url.startswith("https://api.eia.gov/v2/petroleum/pri/spt")

    @pytest.mark.asyncio
    async def test_observation_date_becomes_a_utc_timestamp(self) -> None:
        context, _ = _context(
            _payload(_observation(period="2026-08-14")), EIA_API_KEY="test-eia-key"
        )

        result = await EiaPetroleumSpotIngestor(context).ingest()

        recorded_at = result.prices[0].recorded_at
        assert (recorded_at.year, recorded_at.month, recorded_at.day) == (2026, 8, 14)
        assert recorded_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_api_key_is_sent_as_a_query_parameter(self) -> None:
        context, client = _context(_payload(_observation()), EIA_API_KEY="test-eia-key")

        await EiaPetroleumSpotIngestor(context).ingest()

        assert client.calls[0][1]["api_key"] == "test-eia-key"

    @pytest.mark.asyncio
    async def test_requests_both_tracked_series_in_one_call(self) -> None:
        """One request per run keeps the source's rate limit comfortable."""
        context, client = _context(_payload(_observation()), EIA_API_KEY="test-eia-key")

        await EiaPetroleumSpotIngestor(context).ingest()

        assert len(client.calls) == 1
        params = client.calls[0][1]
        assert params["frequency"] == "daily"

    @pytest.mark.asyncio
    async def test_daily_change_is_computed_from_the_previous_observation(self) -> None:
        context, _ = _context(
            _payload(
                _observation(period="2026-08-14", value=100.0),
                _observation(period="2026-08-13", value=80.0),
            ),
            EIA_API_KEY="test-eia-key",
        )

        result = await EiaPetroleumSpotIngestor(context).ingest()

        newest = next(price for price in result.prices if price.recorded_at.day == 14)
        assert newest.pct_change_1d == Decimal("25.000")

    @pytest.mark.asyncio
    async def test_weekly_change_uses_the_observation_a_week_earlier(self) -> None:
        context, _ = _context(
            _payload(
                _observation(period="2026-08-14", value=110.0),
                _observation(period="2026-08-07", value=100.0),
            ),
            EIA_API_KEY="test-eia-key",
        )

        result = await EiaPetroleumSpotIngestor(context).ingest()

        newest = next(price for price in result.prices if price.recorded_at.day == 14)
        assert newest.pct_change_7d == Decimal("10.000")

    @pytest.mark.asyncio
    async def test_change_is_left_empty_when_there_is_no_earlier_observation(self) -> None:
        context, _ = _context(_payload(_observation()), EIA_API_KEY="test-eia-key")

        result = await EiaPetroleumSpotIngestor(context).ingest()

        assert result.prices[0].pct_change_1d is None
        assert result.prices[0].pct_change_7d is None

    @pytest.mark.asyncio
    async def test_each_series_is_compared_only_against_itself(self) -> None:
        context, _ = _context(
            _payload(
                _observation(series="RWTC", period="2026-08-14", value=100.0),
                _observation(series="RBRTE", period="2026-08-13", value=50.0),
            ),
            EIA_API_KEY="test-eia-key",
        )

        result = await EiaPetroleumSpotIngestor(context).ingest()

        wti = next(price for price in result.prices if price.entity_name == "WTI_Crude")
        assert wti.pct_change_1d is None

    @pytest.mark.asyncio
    async def test_an_empty_response_is_not_an_error(self) -> None:
        context, _ = _context(_payload(), EIA_API_KEY="test-eia-key")

        result = await EiaPetroleumSpotIngestor(context).ingest()

        assert result.record_count == 0
        assert result.source_name == "eia.gov"


class TestMalformedPayload:
    @pytest.mark.asyncio
    async def test_missing_response_object_is_rejected(self) -> None:
        context, _ = _context({"unexpected": True}, EIA_API_KEY="test-eia-key")

        with pytest.raises(ValidationError):
            await EiaPetroleumSpotIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_a_body_that_is_not_an_object_is_rejected(self) -> None:
        context, _ = _context("<html>maintenance</html>", EIA_API_KEY="test-eia-key")

        with pytest.raises(ValidationError):
            await EiaPetroleumSpotIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_an_unparseable_price_is_rejected(self) -> None:
        context, _ = _context(
            _payload({"series": "RWTC", "period": "2026-08-14", "value": "n/a"}),
            EIA_API_KEY="test-eia-key",
        )

        with pytest.raises(ValidationError):
            await EiaPetroleumSpotIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_an_unparseable_date_is_rejected(self) -> None:
        context, _ = _context(
            _payload(_observation(period="last tuesday")), EIA_API_KEY="test-eia-key"
        )

        with pytest.raises(ValidationError):
            await EiaPetroleumSpotIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_a_reporting_gap_is_skipped_rather_than_stored_as_zero(self) -> None:
        """EIA publishes null on holidays; storing that as a price would be wrong."""
        context, _ = _context(
            _payload(
                _observation(period="2026-08-14", value=None),
                _observation(period="2026-08-13", value=78.0),
            ),
            EIA_API_KEY="test-eia-key",
        )

        result = await EiaPetroleumSpotIngestor(context).ingest()

        assert [price.recorded_at.day for price in result.prices] == [13]

    @pytest.mark.asyncio
    async def test_series_the_platform_does_not_track_are_ignored(self) -> None:
        context, _ = _context(
            _payload(
                _observation(series="EMM_EPM0_PTE_NUS_DPG", period="2026-08-14", value=3.1),
                _observation(series="RWTC", period="2026-08-14", value=78.0),
            ),
            EIA_API_KEY="test-eia-key",
        )

        result = await EiaPetroleumSpotIngestor(context).ingest()

        assert [price.entity_name for price in result.prices] == ["WTI_Crude"]
