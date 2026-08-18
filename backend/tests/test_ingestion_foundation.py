"""Tests for the ingestion interfaces, the source registry, and the HTTP client."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.http import HttpError, HttpxClient
from shadow_cpi.ingestion.registry import SourceRegistry
from shadow_cpi.shared import CommodityPrice, IngestionMethod, Sector

RECORDED_AT = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)

SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "test-gemini-key",
        "BRIGHTDATA_API_KEY": "test-brightdata-key",
        "NEO4J_PASSWORD": "test-neo4j-password",
        "CRON_SECRET": "test-cron-secret",
        "EIA_API_KEY": "test-eia-key",
    }
)


def _price(entity_name: str = "WTI_Crude") -> CommodityPrice:
    return CommodityPrice(
        entity_name=entity_name,
        sector=Sector.ENERGY,
        price=Decimal("78.21"),
        currency="USD",
        unit="barrel",
        recorded_at=RECORDED_AT,
        source_name="eia.gov",
        source_url="https://api.eia.gov/v2/petroleum/pri/spt/data",
        ingestion_method=IngestionMethod.OFFICIAL_API,
    )


class StubIngestor:
    """Minimal ingestor used to exercise the registry."""

    source_id = "stub_source"
    source_name = "stub.example"

    def __init__(self, context: IngestionContext) -> None:
        self.context = context

    async def ingest(self) -> IngestionResult:
        return IngestionResult(source_name=self.source_name, prices=(_price(),))


class TestIngestionResult:
    def test_counts_every_record_it_carries(self) -> None:
        result = IngestionResult(
            source_name="eia.gov",
            prices=(_price("WTI_Crude"), _price("Brent_Crude")),
        )

        assert result.record_count == 2

    def test_an_empty_result_is_valid_and_reports_zero(self) -> None:
        """A source with nothing new to report is normal, not an error."""
        result = IngestionResult(source_name="eia.gov")

        assert result.record_count == 0
        assert result.prices == ()
        assert result.holdings == ()

    def test_result_is_immutable(self) -> None:
        result = IngestionResult(source_name="eia.gov")

        with pytest.raises(AttributeError):
            result.source_name = "other"  # type: ignore[misc]


class TestSourceRegistry:
    def test_registered_source_can_be_built(self) -> None:
        registry = SourceRegistry()
        registry.register(StubIngestor.source_id, StubIngestor)

        ingestor = registry.build("stub_source", IngestionContext(http=None, settings=SETTINGS))  # type: ignore[arg-type]

        assert isinstance(ingestor, StubIngestor)

    def test_registering_the_same_identifier_twice_is_refused(self) -> None:
        """A silent overwrite would mean one source quietly stops running."""
        registry = SourceRegistry()
        registry.register("stub_source", StubIngestor)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("stub_source", StubIngestor)

    def test_unknown_identifier_reports_what_is_available(self) -> None:
        registry = SourceRegistry()
        registry.register("stub_source", StubIngestor)

        with pytest.raises(KeyError, match="stub_source"):
            registry.build("nope", IngestionContext(http=None, settings=SETTINGS))  # type: ignore[arg-type]

    def test_lists_sources_in_a_stable_order(self) -> None:
        registry = SourceRegistry()
        registry.register("zulu", StubIngestor)
        registry.register("alpha", StubIngestor)

        assert registry.source_ids() == ("alpha", "zulu")

    def test_builds_every_registered_source_at_once(self) -> None:
        """This is what the scheduler calls; adding a source needs no change here."""
        registry = SourceRegistry()
        registry.register("alpha", StubIngestor)
        registry.register("zulu", StubIngestor)

        built = registry.build_all(IngestionContext(http=None, settings=SETTINGS))  # type: ignore[arg-type]

        assert len(built) == 2

    def test_decorator_registers_a_source(self) -> None:
        registry = SourceRegistry()

        @registry.source("decorated")
        class Decorated(StubIngestor):
            source_id = "decorated"

        assert registry.source_ids() == ("decorated",)
        assert Decorated.source_id == "decorated"


class TestHttpxClient:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_json_returns_the_decoded_body(self) -> None:
        respx.get("https://api.example/data").mock(
            return_value=httpx.Response(200, json={"value": 1})
        )

        async with HttpxClient() as client:
            body = await client.get_json("https://api.example/data")

        assert body == {"value": 1}

    @pytest.mark.asyncio
    @respx.mock
    async def test_query_parameters_and_headers_are_sent(self) -> None:
        route = respx.get("https://api.example/data").mock(
            return_value=httpx.Response(200, json={})
        )

        async with HttpxClient() as client:
            await client.get_json(
                "https://api.example/data",
                params={"api_key": "secret"},
                headers={"User-Agent": "ShadowCPI/1.0 (dev@example.com)"},
            )

        request = route.calls[0].request
        assert request.url.params["api_key"] == "secret"
        assert request.headers["User-Agent"] == "ShadowCPI/1.0 (dev@example.com)"

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_query_string_already_in_the_url_is_kept(self) -> None:
        """Passing no query values must not wipe the ones the caller put in the URL."""
        route = respx.get("https://api.example/result").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        async with HttpxClient() as client:
            await client.get_json("https://api.example/result?response_id=d2t1")

        assert route.calls[0].request.url.params["response_id"] == "d2t1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_query_values_can_still_be_supplied_separately(self) -> None:
        route = respx.get("https://api.example/data").mock(
            return_value=httpx.Response(200, json={})
        )

        async with HttpxClient() as client:
            await client.get_json("https://api.example/data", params={"page": 2})

        assert route.calls[0].request.url.params["page"] == "2"

    @pytest.mark.asyncio
    @respx.mock
    async def test_error_status_raises_with_the_url_and_status(self) -> None:
        respx.get("https://api.example/data").mock(return_value=httpx.Response(503))

        async with HttpxClient() as client:
            with pytest.raises(HttpError, match="503"):
                await client.get_json("https://api.example/data")

    @pytest.mark.asyncio
    @respx.mock
    async def test_error_message_never_repeats_secret_query_values(self) -> None:
        """An upstream failure must not leak an API key into logs."""
        respx.get("https://api.example/data").mock(return_value=httpx.Response(500))

        async with HttpxClient() as client:
            with pytest.raises(HttpError) as error:
                await client.get_json(
                    "https://api.example/data", params={"api_key": "super-secret"}
                )

        assert "super-secret" not in str(error.value)

    @pytest.mark.asyncio
    @respx.mock
    async def test_invalid_json_is_reported_as_a_source_problem(self) -> None:
        respx.get("https://api.example/data").mock(
            return_value=httpx.Response(200, text="<html>maintenance</html>")
        )

        async with HttpxClient() as client:
            with pytest.raises(HttpError, match="JSON"):
                await client.get_json("https://api.example/data")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_text_returns_the_raw_body(self) -> None:
        respx.get("https://api.example/page").mock(
            return_value=httpx.Response(200, text="CIK,NAME\n123,ACME")
        )

        async with HttpxClient() as client:
            body = await client.get_text("https://api.example/page")

        assert body.startswith("CIK,NAME")

    @pytest.mark.asyncio
    @respx.mock
    async def test_a_network_failure_is_reported_as_an_http_error(self) -> None:
        respx.get("https://api.example/data").mock(side_effect=httpx.ConnectError("boom"))

        async with HttpxClient() as client:
            with pytest.raises(HttpError, match="api.example"):
                await client.get_json("https://api.example/data")

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_json_sends_the_body_and_returns_the_reply(self) -> None:
        route = respx.post("https://api.example/jobs").mock(
            return_value=httpx.Response(200, json={"status": "started"})
        )

        async with HttpxClient() as client:
            reply = await client.post_json(
                "https://api.example/jobs",
                body={"collector": "copper"},
                headers={"Authorization": "Bearer token"},
            )

        assert reply == {"status": "started"}
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer token"
        assert b'"collector"' in request.content

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_accepts_an_empty_reply_body(self) -> None:
        """Some job endpoints acknowledge with no content at all."""
        respx.post("https://api.example/jobs").mock(return_value=httpx.Response(204))

        async with HttpxClient() as client:
            reply = await client.post_json("https://api.example/jobs", body={})

        assert reply is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_error_status_is_reported_without_the_credential(self) -> None:
        respx.post("https://api.example/jobs").mock(return_value=httpx.Response(401))

        async with HttpxClient() as client:
            with pytest.raises(HttpError, match="401") as error:
                await client.post_json(
                    "https://api.example/jobs",
                    body={},
                    headers={"Authorization": "Bearer super-secret"},
                )

        assert "super-secret" not in str(error.value)
