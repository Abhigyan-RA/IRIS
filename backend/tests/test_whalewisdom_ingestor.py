"""Tests for WhaleWisdom's bounded, self-healing institutional enrichment path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

import pytest

from shadow_cpi.config import build_settings
from shadow_cpi.ingestion.base import IngestionContext
from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome
from shadow_cpi.ingestion.brightdata.whalewisdom import (
    DEFAULT_WHALEWISDOM_FUNDS,
    WHALEWISDOM_SOURCE_ID,
    WhaleWisdomIngestor,
)

COLLECTOR = "c_whale"
SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "gemini-test",
        "BRIGHTDATA_API_KEY": "brightdata-test",
        "SCRAPER_STUDIO_COLLECTORS": f"{WHALEWISDOM_SOURCE_ID}={COLLECTOR}",
        "CRON_SECRET": "cron-test",
        "NEO4J_PASSWORD": "neo4j-test",
    }
)

LIVE_PAYLOAD: list[Mapping[str, object]] = [
    {
        "quarter": "2026-06-30",
        "total_holdings": "$20.2b, Prior: $13.7b",
        "holdings_count": "1-25 of 509",
        "holdings": [
            {
                "name": "NVIDIA Corporation",
                "ticker": "NVDA",
                "shares": "2,495,344",
                "market_value": "5,673,738,513",
                "portfolio_percent": "28.52%",
                "change_in_shares": "1,355,225",
                "percent_change": "+118.86%",
            },
            {
                "name": "Micron Technology, Inc.",
                "ticker": "MU",
                "shares": "4,828,786",
                "market_value": "5,573,819,392",
                "portfolio_percent": "28.01%",
                "change_in_shares": "4,811,424",
                "percent_change": "New",
            },
        ],
        "product_page_url": "https://whalewisdom.com/filer/bridgewater-associates-lp",
    }
]


class UnusedHttpClient:
    async def get_json(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("the injected runner owns scraping")

    async def get_text(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("the injected runner owns scraping")

    async def post_json(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("the injected runner owns scraping")


class FakeRunner:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self._rows = list(rows)
        self.calls: list[tuple[str, str, str]] = []

    async def run(self, collector_id: str, source_name: str, url: str) -> RunOutcome:
        self.calls.append((collector_id, source_name, url))
        return RunOutcome(rows=list(self._rows), healed=False, reason="healthy")


def _ingestor(
    rows: Sequence[Mapping[str, object]] = LIVE_PAYLOAD,
) -> tuple[WhaleWisdomIngestor, FakeRunner]:
    runner = FakeRunner(rows)
    context = IngestionContext(http=UnusedHttpClient(), settings=SETTINGS)  # type: ignore[arg-type]
    return WhaleWisdomIngestor(context, runner=runner, funds=DEFAULT_WHALEWISDOM_FUNDS[:1]), runner


class TestConfiguration:
    def test_source_has_a_stable_id_for_configuration_and_health_events(self) -> None:
        ingestor, _ = _ingestor()

        assert ingestor.source_id == "whalewisdom_13f_scraper"
        assert ingestor.source_name == "whalewisdom.com"

    def test_source_is_ready_only_when_a_studio_collector_is_registered(self) -> None:
        ingestor, _ = _ingestor()
        missing = build_settings(
            {
                "GEMINI_API_KEY": "g",
                "BRIGHTDATA_API_KEY": "b",
                "CRON_SECRET": "c",
                "NEO4J_PASSWORD": "n",
            }
        )
        unconfigured = WhaleWisdomIngestor(
            IngestionContext(http=UnusedHttpClient(), settings=missing),  # type: ignore[arg-type]
            runner=FakeRunner(LIVE_PAYLOAD),
            funds=DEFAULT_WHALEWISDOM_FUNDS[:1],
        )

        assert ingestor.is_configured is True
        assert unconfigured.is_configured is False

    def test_default_watchlist_matches_the_official_sec_watchlist(self) -> None:
        assert {(fund.cik, fund.name) for fund in DEFAULT_WHALEWISDOM_FUNDS} == {
            ("0001350694", "Bridgewater Associates"),
            ("0001067983", "Berkshire Hathaway"),
        }


class TestCollection:
    @pytest.mark.asyncio
    async def test_the_configured_collector_runs_for_the_configured_filer_page(self) -> None:
        ingestor, runner = _ingestor()

        await ingestor.ingest()

        assert runner.calls == [
            (
                COLLECTOR,
                "whalewisdom.com",
                "https://whalewisdom.com/filer/bridgewater-associates-lp#tabholdings_tab",
            )
        ]

    @pytest.mark.asyncio
    async def test_maps_the_verified_fund_summary_without_inference(self) -> None:
        ingestor, _ = _ingestor()

        result = await ingestor.ingest()

        assert len(result.fund_snapshots) == 1
        summary = result.fund_snapshots[0]
        assert summary.filer_cik == "0001350694"
        assert summary.report_period == date(2026, 6, 30)
        assert summary.reported_value_usd == Decimal("20200000000")
        assert summary.holdings_count == 509
        assert summary.whale_score is None

    @pytest.mark.asyncio
    async def test_maps_each_visible_holding_to_separate_enrichment(self) -> None:
        ingestor, _ = _ingestor()

        result = await ingestor.ingest()

        assert [row.stock_ticker for row in result.holding_enrichments] == ["NVDA", "MU"]
        nvidia = result.holding_enrichments[0]
        assert nvidia.stock_name == "NVIDIA Corporation"
        assert nvidia.rank == 1
        assert nvidia.reported_pct_change_shares == Decimal("118.86")
        assert nvidia.quarter_end == date(2026, 6, 30)

    @pytest.mark.asyncio
    async def test_commercial_rows_never_enter_the_official_holdings_ledger(self) -> None:
        ingestor, _ = _ingestor()

        result = await ingestor.ingest()

        assert result.holdings == ()
        assert result.prices == ()

    @pytest.mark.asyncio
    async def test_unusable_tickers_are_skipped_instead_of_repaired(self) -> None:
        payload = [
            {
                "quarter": "2026-06-30",
                "holdings": [{"name": "No ticker"}, {"ticker": "bad symbol!"}],
            }
        ]
        ingestor, _ = _ingestor(payload)

        result = await ingestor.ingest()

        assert result.holding_enrichments == ()
        assert len(result.fund_snapshots) == 1

    @pytest.mark.asyncio
    async def test_a_failed_self_heal_returns_no_partial_data(self) -> None:
        ingestor, _ = _ingestor([])

        result = await ingestor.ingest()

        assert result.record_count == 0

    @pytest.mark.asyncio
    async def test_every_enrichment_carries_the_exact_page_and_method(self) -> None:
        ingestor, _ = _ingestor()

        result = await ingestor.ingest()

        row = result.holding_enrichments[0]
        assert row.source_url.endswith("bridgewater-associates-lp#tabholdings_tab")
        assert row.source_name == "whalewisdom.com"
        assert row.ingestion_method.value == "brightdata_scrape"
