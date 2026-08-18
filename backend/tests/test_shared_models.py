"""Tests for the domain models that every data source is normalized into."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from shadow_cpi.shared import (
    CommodityPrice,
    IngestionMethod,
    InstitutionalHolding,
    PipelineEventType,
    PipelineHealthEvent,
    Sector,
    normalize_cik,
)

RECORDED_AT = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)


def _price(**overrides: object) -> CommodityPrice:
    payload: dict[str, object] = {
        "entity_name": "Copper",
        "sector": Sector.METALS,
        "price": Decimal("4.52"),
        "currency": "USD",
        "unit": "lb",
        "pct_change_1d": Decimal("1.8"),
        "recorded_at": RECORDED_AT,
        "source_name": "investing.com",
        "source_url": "https://www.investing.com/commodities/copper",
        "ingestion_method": IngestionMethod.BRIGHTDATA_SCRAPE,
    }
    payload.update(overrides)
    return CommodityPrice(**payload)  # type: ignore[arg-type]


class TestCommodityPrice:
    def test_accepts_a_complete_row(self) -> None:
        price = _price()

        assert price.entity_name == "Copper"
        assert price.sector is Sector.METALS
        assert price.price == Decimal("4.52")
        assert price.pct_change_7d is None

    def test_currency_must_be_a_three_letter_code(self) -> None:
        with pytest.raises(ValidationError):
            _price(currency="US Dollars")

    def test_lowercase_currency_is_rejected_rather_than_upcased(self) -> None:
        """Silently fixing input hides upstream bugs, so it is refused instead."""
        with pytest.raises(ValidationError):
            _price(currency="usd")

    def test_entity_name_cannot_be_blank(self) -> None:
        with pytest.raises(ValidationError):
            _price(entity_name="   ")

    def test_unknown_sector_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _price(sector="crypto")

    def test_unknown_ingestion_method_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _price(ingestion_method="carrier_pigeon")

    def test_negative_price_is_allowed(self) -> None:
        """Crude oil traded below zero in April 2020; the data must survive that."""
        assert _price(price=Decimal("-37.63")).price == Decimal("-37.63")

    def test_price_beyond_stored_precision_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _price(price=Decimal("1.123456"))

    def test_price_beyond_stored_magnitude_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _price(price=Decimal("12345678901.0"))

    def test_source_url_must_be_http_or_https(self) -> None:
        with pytest.raises(ValidationError):
            _price(source_url="javascript:alert(1)")

    def test_naive_timestamp_is_rejected(self) -> None:
        """A timestamp without a timezone is ambiguous across deployments."""
        with pytest.raises(ValidationError):
            _price(recorded_at=datetime(2026, 8, 15, 9, 0))

    def test_non_utc_timestamp_is_converted_to_utc(self) -> None:
        from datetime import timedelta, timezone

        tokyo = timezone(timedelta(hours=9))

        price = _price(recorded_at=datetime(2026, 8, 15, 18, 0, tzinfo=tokyo))

        assert price.recorded_at == RECORDED_AT

    def test_unit_must_look_like_an_identifier(self) -> None:
        with pytest.raises(ValidationError):
            _price(unit="metric ton; DROP TABLE")

    def test_model_is_immutable(self) -> None:
        price = _price()

        with pytest.raises(ValidationError):
            price.price = Decimal("5")  # type: ignore[misc]


class TestNormalizeCik:
    def test_pads_a_short_number_to_ten_digits(self) -> None:
        assert normalize_cik("1350694") == "0001350694"

    def test_keeps_an_already_padded_number(self) -> None:
        assert normalize_cik("0001350694") == "0001350694"

    def test_strips_a_cik_prefix_and_whitespace(self) -> None:
        assert normalize_cik("  CIK0001350694 ") == "0001350694"

    def test_accepts_an_integer(self) -> None:
        assert normalize_cik(1350694) == "0001350694"

    @pytest.mark.parametrize("value", ["", "   ", "abc", "12345678901", "-1"])
    def test_rejects_values_that_are_not_a_cik(self, value: str) -> None:
        with pytest.raises(ValueError, match="CIK"):
            normalize_cik(value)


def _holding(**overrides: object) -> InstitutionalHolding:
    payload: dict[str, object] = {
        "filer_name": "Bridgewater Associates",
        "filer_cik": "0001350694",
        "stock_ticker": "NVDA",
        "shares_held": 1_200_000,
        "market_value_usd": Decimal("144000000.00"),
        "pct_portfolio": Decimal("7.02"),
        "shares_change_qoq": 150_000,
        "quarter_end": date(2026, 6, 30),
        "source_url": "https://www.sec.gov/edgar/browse/?CIK=0001350694",
    }
    payload.update(overrides)
    return InstitutionalHolding(**payload)  # type: ignore[arg-type]


class TestInstitutionalHolding:
    def test_accepts_a_complete_row(self) -> None:
        holding = _holding()

        assert holding.filer_cik == "0001350694"
        assert holding.shares_change_qoq == 150_000

    def test_cik_is_normalized_to_ten_digits(self) -> None:
        assert _holding(filer_cik="1350694").filer_cik == "0001350694"

    def test_ticker_is_rejected_when_it_is_not_a_symbol(self) -> None:
        with pytest.raises(ValidationError):
            _holding(stock_ticker="nvda inc")

    def test_shares_held_cannot_be_negative(self) -> None:
        with pytest.raises(ValidationError):
            _holding(shares_held=-1)

    def test_position_reduction_is_recorded_as_a_negative_change(self) -> None:
        assert _holding(shares_change_qoq=-40_000).shares_change_qoq == -40_000

    def test_portfolio_percentage_above_one_hundred_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _holding(pct_portfolio=Decimal("101"))

    def test_optional_fields_may_be_absent(self) -> None:
        holding = _holding(market_value_usd=None, pct_portfolio=None, source_url=None)

        assert holding.market_value_usd is None
        assert holding.source_url is None


def _event(**overrides: object) -> PipelineHealthEvent:
    payload: dict[str, object] = {
        "scraper_id": "whalewisdom_13f_scraper",
        "source_name": "whalewisdom.com",
        "event_type": PipelineEventType.DOM_SHIFT_DETECTED,
        "message": "[WARNING] price field missing from every row",
        "occurred_at": RECORDED_AT,
    }
    payload.update(overrides)
    return PipelineHealthEvent(**payload)  # type: ignore[arg-type]


class TestPipelineHealthEvent:
    def test_accepts_a_complete_event(self) -> None:
        event = _event()

        assert event.event_type is PipelineEventType.DOM_SHIFT_DETECTED
        assert event.message is not None

    def test_message_is_optional(self) -> None:
        assert _event(message=None).message is None

    def test_unknown_event_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _event(event_type="exploded")

    def test_every_event_type_in_the_lifecycle_is_supported(self) -> None:
        assert {member.value for member in PipelineEventType} == {
            "success",
            "collection_failed",
            "dom_shift_detected",
            "self_heal_triggered",
            "self_heal_resolved",
            "self_heal_failed",
        }

    def test_naive_timestamp_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _event(occurred_at=datetime(2026, 8, 15, 9, 0))
