"""Tests for the USDA grain price ingestor."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.official.usda_mars import (
    ENDPOINT,
    USDA_COMMODITIES,
    UsdaGrainPriceIngestor,
)
from shadow_cpi.shared import IngestionMethod, Sector

BASE_ENV = {
    "GEMINI_API_KEY": "test-gemini-key",
    "BRIGHTDATA_API_KEY": "test-brightdata-key",
    "NEO4J_PASSWORD": "test-neo4j-password",
    "CRON_SECRET": "test-cron-secret",
}


class FakeHttpClient:
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


def _report_row(
    commodity: str = "WHEAT",
    report_date: str = "08/14/2026",
    avg_price: str | None = "6.4500",
    price_unit: str = "$ / BU",
) -> dict[str, Any]:
    return {
        "commodity": commodity,
        "report_date": report_date,
        "avg_price": avg_price,
        "price_unit": price_unit,
    }


def _context(payload: object, **env: str) -> tuple[IngestionContext, FakeHttpClient]:
    client = FakeHttpClient(payload)
    settings = build_settings({**BASE_ENV, **env})
    return IngestionContext(http=client, settings=settings), client


class TestConfiguration:
    def test_source_is_identified_for_schedules_and_logs(self) -> None:
        context, _ = _context([], USDA_MARS_API_KEY="test-usda-key")

        ingestor = UsdaGrainPriceIngestor(context)

        assert ingestor.source_id == "usda_grain_prices"
        assert ingestor.source_name == "mymarketnews.ams.usda.gov"

    def test_is_unconfigured_without_a_key(self) -> None:
        context, _ = _context([])

        assert UsdaGrainPriceIngestor(context).is_configured is False

    @pytest.mark.asyncio
    async def test_unconfigured_run_returns_nothing_and_makes_no_request(self) -> None:
        context, client = _context([_report_row()])

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert result.record_count == 0
        assert client.calls == []

    def test_tracked_commodities_cover_the_staple_crops(self) -> None:
        assert USDA_COMMODITIES["WHEAT"].entity_name == "Wheat"
        assert USDA_COMMODITIES["CORN"].entity_name == "Corn"
        assert USDA_COMMODITIES["SOYBEANS"].entity_name == "Soybeans"


class TestAuthentication:
    @pytest.mark.asyncio
    async def test_key_is_sent_in_the_authorization_header(self) -> None:
        """USDA authenticates with the key as a basic-auth username."""
        context, client = _context([_report_row()], USDA_MARS_API_KEY="test-usda-key")

        await UsdaGrainPriceIngestor(context).ingest()

        header = client.calls[0][2]["Authorization"]
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
        assert decoded == "test-usda-key:"

    @pytest.mark.asyncio
    async def test_key_is_never_placed_in_the_url_or_query_string(self) -> None:
        """A key in a URL ends up in access logs and browser history."""
        context, client = _context([_report_row()], USDA_MARS_API_KEY="test-usda-key")

        await UsdaGrainPriceIngestor(context).ingest()

        url, params, _ = client.calls[0]
        assert "test-usda-key" not in url
        assert all(str(value) != "test-usda-key" for value in params.values())

    @pytest.mark.asyncio
    async def test_reads_the_documented_report_endpoint(self) -> None:
        context, client = _context([_report_row()], USDA_MARS_API_KEY="test-usda-key")

        await UsdaGrainPriceIngestor(context).ingest()

        assert client.calls[0][0].startswith(ENDPOINT)


class TestHealthyPayload:
    @pytest.mark.asyncio
    async def test_maps_a_report_row_to_a_price_record(self) -> None:
        context, _ = _context([_report_row()], USDA_MARS_API_KEY="test-usda-key")

        result = await UsdaGrainPriceIngestor(context).ingest()

        price = result.prices[0]
        assert price.entity_name == "Wheat"
        assert price.sector is Sector.AGRICULTURE
        assert price.price == Decimal("6.4500")
        assert price.unit == "bushel"
        assert price.currency == "USD"
        assert price.ingestion_method is IngestionMethod.OFFICIAL_API

    @pytest.mark.asyncio
    async def test_report_date_is_parsed_from_the_american_format(self) -> None:
        context, _ = _context(
            [_report_row(report_date="08/14/2026")], USDA_MARS_API_KEY="test-usda-key"
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        recorded_at = result.prices[0].recorded_at
        assert (recorded_at.year, recorded_at.month, recorded_at.day) == (2026, 8, 14)

    @pytest.mark.asyncio
    async def test_an_iso_date_is_also_accepted(self) -> None:
        """USDA reports are not consistent about date format between series."""
        context, _ = _context(
            [_report_row(report_date="2026-08-14")], USDA_MARS_API_KEY="test-usda-key"
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert result.prices[0].recorded_at.day == 14

    @pytest.mark.asyncio
    async def test_several_commodities_are_returned_together(self) -> None:
        context, _ = _context(
            [_report_row(commodity="WHEAT"), _report_row(commodity="CORN", avg_price="4.10")],
            USDA_MARS_API_KEY="test-usda-key",
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert {price.entity_name for price in result.prices} == {"Wheat", "Corn"}

    @pytest.mark.asyncio
    async def test_commodity_names_are_matched_regardless_of_case_and_spacing(self) -> None:
        context, _ = _context(
            [_report_row(commodity="  Wheat ")], USDA_MARS_API_KEY="test-usda-key"
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert result.prices[0].entity_name == "Wheat"

    @pytest.mark.asyncio
    async def test_untracked_commodities_are_ignored(self) -> None:
        context, _ = _context(
            [_report_row(commodity="ALPACA FLEECE"), _report_row(commodity="WHEAT")],
            USDA_MARS_API_KEY="test-usda-key",
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert [price.entity_name for price in result.prices] == ["Wheat"]

    @pytest.mark.asyncio
    async def test_an_empty_report_is_not_an_error(self) -> None:
        context, _ = _context([], USDA_MARS_API_KEY="test-usda-key")

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_a_wrapped_results_object_is_also_accepted(self) -> None:
        """Some report endpoints wrap rows in a results object."""
        context, _ = _context({"results": [_report_row()]}, USDA_MARS_API_KEY="test-usda-key")

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert result.prices[0].entity_name == "Wheat"


class TestMalformedPayload:
    @pytest.mark.asyncio
    async def test_a_row_missing_its_price_field_is_rejected(self) -> None:
        context, _ = _context(
            [{"commodity": "WHEAT", "report_date": "08/14/2026"}],
            USDA_MARS_API_KEY="test-usda-key",
        )

        with pytest.raises(ValidationError):
            await UsdaGrainPriceIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_a_non_numeric_price_is_rejected(self) -> None:
        context, _ = _context(
            [_report_row(avg_price="not a price")], USDA_MARS_API_KEY="test-usda-key"
        )

        with pytest.raises(ValidationError):
            await UsdaGrainPriceIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_an_unparseable_date_is_rejected(self) -> None:
        context, _ = _context(
            [_report_row(report_date="week of the 14th")], USDA_MARS_API_KEY="test-usda-key"
        )

        with pytest.raises(ValidationError):
            await UsdaGrainPriceIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_a_body_that_is_not_a_list_or_results_object_is_rejected(self) -> None:
        context, _ = _context("<html>maintenance</html>", USDA_MARS_API_KEY="test-usda-key")

        with pytest.raises(ValidationError):
            await UsdaGrainPriceIngestor(context).ingest()

    @pytest.mark.asyncio
    async def test_rows_with_no_price_reported_are_skipped(self) -> None:
        context, _ = _context(
            [_report_row(avg_price=None), _report_row(commodity="CORN", avg_price="4.10")],
            USDA_MARS_API_KEY="test-usda-key",
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert [price.entity_name for price in result.prices] == ["Corn"]

    @pytest.mark.asyncio
    async def test_an_unrecognised_unit_falls_back_to_the_tracked_default(self) -> None:
        """The price is still correct; only the label is unfamiliar."""
        context, _ = _context(
            [_report_row(price_unit="per truckload")], USDA_MARS_API_KEY="test-usda-key"
        )

        result = await UsdaGrainPriceIngestor(context).ingest()

        assert result.prices[0].unit == "bushel"
