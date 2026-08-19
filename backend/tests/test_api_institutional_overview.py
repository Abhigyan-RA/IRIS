"""Contract tests for the bounded institutional intelligence overview."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from shadow_cpi.api.app import create_app
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import build_settings
from shadow_cpi.shared import (
    IngestionMethod,
    InstitutionalFundSnapshot,
    InstitutionalHolding,
    InstitutionalHoldingEnrichment,
)

SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "test-gemini-key",
        "BRIGHTDATA_API_KEY": "test-brightdata-key",
        "NEO4J_PASSWORD": "test-neo4j-password",
        "CRON_SECRET": "test-cron-secret",
    }
)


def _holding(
    ticker: str,
    fund: tuple[str, str],
    shares: int,
    change: int | None,
    value: str,
) -> InstitutionalHolding:
    filer, cik = fund
    return InstitutionalHolding(
        filer_name=filer,
        filer_cik=cik,
        stock_ticker=ticker,
        shares_held=shares,
        market_value_usd=Decimal(value),
        pct_portfolio=Decimal("12.5"),
        shares_change_qoq=change,
        quarter_end=date(2025, 12, 31),
        source_url=f"https://www.sec.gov/Archives/{cik}",
    )


class FakeInstitutionalReader:
    """Return a complete current view from in-memory rows."""

    def __init__(self) -> None:
        self.holdings = [
            _holding("AAPL", ("Bridgewater", "0001350694"), 100, 20, "2000"),
            _holding("MSFT", ("Bridgewater", "0001350694"), 50, -10, "1500"),
            _holding("AAPL", ("Berkshire", "0001067983"), 300, 30, "6000"),
        ]
        self.snapshots = [
            InstitutionalFundSnapshot(
                filer_name="Bridgewater",
                filer_cik="0001350694",
                report_period=date(2025, 12, 31),
                reported_value_usd=Decimal("3500"),
                holdings_count=2,
                top_10_concentration_pct=Decimal("42.1"),
                source_url="https://whalewisdom.com/filer/bridgewater",
                observed_at=datetime(2026, 2, 16, tzinfo=UTC),
            )
        ]
        self.enrichments = [
            InstitutionalHoldingEnrichment(
                filer_cik="0001350694",
                stock_ticker="AAPL",
                stock_name="Apple Inc",
                quarter_end=date(2025, 12, 31),
                rank=1,
                source_url="https://whalewisdom.com/filer/bridgewater",
                ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
                observed_at=datetime(2026, 2, 16, tzinfo=UTC),
            )
        ]

    async def latest_holdings(self) -> list[InstitutionalHolding]:
        return self.holdings

    async def latest_fund_snapshots(self) -> list[InstitutionalFundSnapshot]:
        return self.snapshots

    async def latest_holding_enrichments(self) -> list[InstitutionalHoldingEnrichment]:
        return self.enrichments


def _client(reader: FakeInstitutionalReader | None = None) -> TestClient:
    app = create_app(SETTINGS, dependencies=ApiDependencies(institutional=reader))
    return TestClient(app)


def test_overview_aggregates_all_current_official_positions_and_joins_enrichment() -> None:
    body = _client(FakeInstitutionalReader()).get("/api/institutional/overview").json()

    assert body["quarter_end"] == "2025-12-31"
    assert body["total_funds"] == 2
    assert body["total_stocks"] == 2
    assert body["total_positions"] == 3
    assert body["funds"][0]["reported_value_usd"] == "6000"
    assert body["stocks"][0] == {
        "stock_ticker": "AAPL",
        "stock_name": "Apple Inc",
        "holder_count": 2,
        "shares_held": 400,
        "market_value_usd": "8000",
        "shares_change_qoq": 50,
        "enriched_positions": 1,
    }
    bridgewater = next(row for row in body["funds"] if row["filer_cik"] == "0001350694")
    assert bridgewater["enrichment"]["source_name"] == "whalewisdom.com"
    assert bridgewater["source_name"] == "SEC EDGAR"
    assert body["enrichment_coverage"]["matched_positions"] == 1
    assert "configured WhaleWisdom watchlist" in body["coverage_note"]
    assert "quarterly" in body["coverage_note"]
    assert "long-only" in body["coverage_note"]


def test_overview_returns_ranked_buys_and_sells_from_official_share_changes() -> None:
    body = _client(FakeInstitutionalReader()).get("/api/institutional/overview").json()

    assert [row["shares_change_qoq"] for row in body["top_buys"]] == [30, 20]
    assert body["top_sells"][0]["shares_change_qoq"] == -10
    assert all(row["source_name"] == "SEC EDGAR" for row in body["top_buys"])


def test_overview_caps_lists_and_rejects_unbounded_limits() -> None:
    client = _client(FakeInstitutionalReader())

    body = client.get(
        "/api/institutional/overview",
        params={"fund_limit": 1, "stock_limit": 1, "mover_limit": 1},
    ).json()

    assert len(body["funds"]) == 1
    assert len(body["stocks"]) == 1
    assert len(body["top_buys"]) == 1
    assert body["total_funds"] == 2
    assert (
        client.get("/api/institutional/overview", params={"stock_limit": 1001}).status_code == 422
    )


def test_overview_has_an_explicit_empty_and_unavailable_state() -> None:
    empty = FakeInstitutionalReader()
    empty.holdings = []
    empty.snapshots = []
    empty.enrichments = []

    body = _client(empty).get("/api/institutional/overview").json()

    assert body["quarter_end"] is None
    assert body["funds"] == []
    assert body["coverage_note"]
    assert _client().get("/api/institutional/overview").status_code == 503
