"""Contract tests for the price endpoints: the risk map and one entity's trend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from shadow_cpi.api.app import create_app
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.config import build_settings
from shadow_cpi.shared import CommodityPrice, IngestionMethod, Sector

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

SETTINGS = build_settings(
    {
        "GEMINI_API_KEY": "test-gemini-key",
        "BRIGHTDATA_API_KEY": "test-brightdata-key",
        "NEO4J_PASSWORD": "test-neo4j-password",
        "CRON_SECRET": "test-cron-secret",
    }
)


def _price(
    entity_name: str = "Copper",
    sector: Sector = Sector.METALS,
    price: str = "4.52",
    change_1d: str | None = "1.8",
    recorded_at: datetime = NOW,
) -> CommodityPrice:
    return CommodityPrice(
        entity_name=entity_name,
        sector=sector,
        price=Decimal(price),
        currency="USD",
        unit="lb",
        pct_change_1d=None if change_1d is None else Decimal(change_1d),
        recorded_at=recorded_at,
        source_name="investing.com",
        source_url="https://www.investing.com/commodities/copper",
        ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
    )


class FakePriceReader:
    """Serves canned prices and records how it was queried."""

    def __init__(
        self,
        by_sector: dict[Sector, list[CommodityPrice]] | None = None,
        history: list[CommodityPrice] | None = None,
        latest: CommodityPrice | None = None,
    ) -> None:
        self._by_sector = by_sector or {}
        self._history = history or []
        self._latest = latest
        self.history_calls: list[tuple[str, int]] = []
        self.latest_calls: list[str] = []

    async def latest_price(self, entity_name: str) -> CommodityPrice | None:
        self.latest_calls.append(entity_name)
        return self._latest

    async def price_history(self, entity_name: str, days: int) -> list[CommodityPrice]:
        self.history_calls.append((entity_name, days))
        return self._history

    async def latest_prices_by_sector(self, sector: Sector) -> list[CommodityPrice]:
        return self._by_sector.get(sector, [])


def _client(prices: FakePriceReader) -> TestClient:
    app = create_app(SETTINGS, dependencies=ApiDependencies(prices=prices))
    return TestClient(app)


class TestRiskMap:
    def test_returns_one_group_per_sector_that_has_data(self) -> None:
        client = _client(
            FakePriceReader(
                by_sector={
                    Sector.METALS: [_price("Copper")],
                    Sector.ENERGY: [_price("WTI_Crude", Sector.ENERGY, "78.21")],
                }
            )
        )

        body = client.get("/api/risk-map").json()

        assert {group["sector"] for group in body["sectors"]} == {"metals", "energy"}

    def test_each_entry_carries_the_numbers_the_map_renders(self) -> None:
        client = _client(FakePriceReader(by_sector={Sector.METALS: [_price("Copper")]}))

        entry = client.get("/api/risk-map").json()["sectors"][0]["entries"][0]

        assert entry["entity_name"] == "Copper"
        assert entry["price"] == "4.52"
        assert entry["currency"] == "USD"
        assert entry["pct_change_1d"] == "1.8"
        assert entry["source_url"].startswith("https://")

    def test_every_entry_says_where_the_number_came_from(self) -> None:
        """No unattributed numbers: each one links back to its source."""
        client = _client(FakePriceReader(by_sector={Sector.METALS: [_price("Copper")]}))

        entry = client.get("/api/risk-map").json()["sectors"][0]["entries"][0]

        assert entry["source_name"] == "investing.com"
        assert entry["ingestion_method"] == "brightdata_scrape"

    def test_entries_are_ordered_by_the_largest_move_first(self) -> None:
        client = _client(
            FakePriceReader(
                by_sector={
                    Sector.METALS: [
                        _price("Copper", change_1d="1.8"),
                        _price("Steel_HRC_US", change_1d="-8.4"),
                        _price("Aluminium", change_1d=None),
                    ]
                }
            )
        )

        entries = client.get("/api/risk-map").json()["sectors"][0]["entries"]

        assert [entry["entity_name"] for entry in entries] == [
            "Steel_HRC_US",
            "Copper",
            "Aluminium",
        ]

    def test_a_region_is_reported_for_the_map(self) -> None:
        client = _client(FakePriceReader(by_sector={Sector.METALS: [_price("Steel_HRC_US")]}))

        entry = client.get("/api/risk-map").json()["sectors"][0]["entries"][0]

        assert entry["region"] == "North America"

    def test_an_unmapped_entity_is_reported_as_global(self) -> None:
        client = _client(FakePriceReader(by_sector={Sector.METALS: [_price("Unobtainium")]}))

        entry = client.get("/api/risk-map").json()["sectors"][0]["entries"][0]

        assert entry["region"] == "Global"

    def test_a_price_older_than_its_freshness_target_is_flagged_stale(self) -> None:
        """A visibly stale number is safe; a silently stale one is not."""
        client = _client(
            FakePriceReader(
                by_sector={
                    Sector.ENERGY: [
                        _price(
                            "WTI_Crude",
                            Sector.ENERGY,
                            recorded_at=datetime.now(UTC) - timedelta(hours=9),
                        )
                    ]
                }
            )
        )

        entry = client.get("/api/risk-map").json()["sectors"][0]["entries"][0]

        assert entry["is_stale"] is True

    def test_a_recent_price_is_not_flagged_stale(self) -> None:
        client = _client(
            FakePriceReader(
                by_sector={
                    Sector.ENERGY: [
                        _price(
                            "WTI_Crude",
                            Sector.ENERGY,
                            recorded_at=datetime.now(UTC) - timedelta(minutes=30),
                        )
                    ]
                }
            )
        )

        entry = client.get("/api/risk-map").json()["sectors"][0]["entries"][0]

        assert entry["is_stale"] is False

    def test_sectors_with_no_data_are_omitted_rather_than_shown_empty(self) -> None:
        client = _client(FakePriceReader(by_sector={Sector.METALS: [_price("Copper")]}))

        body = client.get("/api/risk-map").json()

        assert len(body["sectors"]) == 1

    def test_an_empty_database_returns_an_empty_map_not_an_error(self) -> None:
        response = _client(FakePriceReader()).get("/api/risk-map")

        assert response.status_code == 200
        assert response.json()["sectors"] == []

    def test_the_response_says_when_it_was_generated(self) -> None:
        client = _client(FakePriceReader(by_sector={Sector.METALS: [_price("Copper")]}))

        body = client.get("/api/risk-map").json()

        assert datetime.fromisoformat(body["generated_at"]).tzinfo is not None


class TestCommodityTrend:
    def test_returns_the_history_for_one_entity(self) -> None:
        history = [
            _price(recorded_at=NOW - timedelta(days=2), price="4.00"),
            _price(recorded_at=NOW - timedelta(days=1), price="4.20"),
            _price(recorded_at=NOW, price="4.52"),
        ]
        client = _client(FakePriceReader(history=history, latest=history[-1]))

        body = client.get("/api/commodities/Copper/trend").json()

        assert body["entity_name"] == "Copper"
        assert [point["price"] for point in body["points"]] == ["4.00", "4.20", "4.52"]

    def test_the_window_defaults_to_thirty_days(self) -> None:
        prices = FakePriceReader(history=[_price()], latest=_price())
        client = _client(prices)

        client.get("/api/commodities/Copper/trend")

        assert prices.history_calls == [("Copper", 30)]

    def test_the_window_can_be_chosen(self) -> None:
        prices = FakePriceReader(history=[_price()], latest=_price())
        client = _client(prices)

        client.get("/api/commodities/Copper/trend", params={"days": 7})

        assert prices.history_calls == [("Copper", 7)]

    def test_a_window_of_zero_is_refused(self) -> None:
        client = _client(FakePriceReader(history=[_price()]))

        assert client.get("/api/commodities/Copper/trend", params={"days": 0}).status_code == 422

    def test_an_absurdly_long_window_is_refused(self) -> None:
        """The cap protects the database from a single expensive request."""
        client = _client(FakePriceReader(history=[_price()]))

        assert client.get("/api/commodities/Copper/trend", params={"days": 5000}).status_code == 422

    def test_change_over_the_window_is_computed(self) -> None:
        history = [
            _price(recorded_at=NOW - timedelta(days=1), price="4.00"),
            _price(recorded_at=NOW, price="5.00"),
        ]
        client = _client(FakePriceReader(history=history, latest=history[-1]))

        body = client.get("/api/commodities/Copper/trend").json()

        assert body["change_pct_over_window"] == "25.000"

    def test_an_untracked_entity_returns_not_found(self) -> None:
        response = _client(FakePriceReader()).get("/api/commodities/Unobtainium/trend")

        assert response.status_code == 404
        assert "Unobtainium" in response.json()["detail"]

    def test_a_single_observation_has_no_window_change(self) -> None:
        client = _client(FakePriceReader(history=[_price()], latest=_price()))

        body = client.get("/api/commodities/Copper/trend").json()

        assert body["change_pct_over_window"] is None

    def test_entity_names_with_spaces_are_accepted(self) -> None:
        prices = FakePriceReader(history=[_price("Stator Coil")], latest=_price("Stator Coil"))
        client = _client(prices)

        client.get("/api/commodities/Stator%20Coil/trend")

        assert prices.history_calls[0][0] == "Stator Coil"
