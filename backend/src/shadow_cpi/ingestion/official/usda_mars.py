"""Bulk grain prices from the USDA Market News service.

Wheat, corn, and soybean prices feed directly into food manufacturing and animal
feed costs, so a move here shows up on grocery shelves months later. USDA
publishes them as official JSON, which is preferable to scraping for the same
reasons as the energy source: stable, free, and unambiguous.

Two quirks of this API are handled here rather than left to callers:

- The key is sent as a basic-auth username with an empty password, which is what
  the service expects. It is never placed in the URL, because URLs end up in
  access logs.
- Report rows are not consistent between series: dates appear in both American and
  ISO form, and unit labels vary in spacing and punctuation.

Free API key: https://mymarketnews.ams.usda.gov/mymarketnews-api
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.shared import CommodityPrice, IngestionMethod, Sector

ENDPOINT = "https://marsapi.ams.usda.gov/services/v1.2/reports"

SOURCE_ID = "usda_grain_prices"
SOURCE_NAME = "mymarketnews.ams.usda.gov"

# National Grain Market Summary. Other reports are added by registering another
# ingestor, so this one stays simple and predictable.
REPORT_SLUG = "2903"

# Date formats seen across USDA report series, tried in order.
_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


@dataclass(frozen=True, slots=True)
class TrackedCommodity:
    """A commodity this platform stores.

    Attributes:
        entity_name: Name used in our own data, for example ``Wheat``.
        unit: Unit to record when the report's own label is not recognised.
    """

    entity_name: str
    unit: str


# USDA commodity labels, mapped to how we store them. Keys are upper case and
# stripped, since the reports are inconsistent about both.
USDA_COMMODITIES: dict[str, TrackedCommodity] = {
    "WHEAT": TrackedCommodity(entity_name="Wheat", unit="bushel"),
    "CORN": TrackedCommodity(entity_name="Corn", unit="bushel"),
    "SOYBEANS": TrackedCommodity(entity_name="Soybeans", unit="bushel"),
}

# Unit labels as they appear in reports, mapped to our own vocabulary.
_UNIT_LABELS: dict[str, str] = {
    "$ / BU": "bushel",
    "$/BU": "bushel",
    "$ PER BUSHEL": "bushel",
    "$ / CWT": "hundredweight",
    "$/CWT": "hundredweight",
    "$ / TON": "short_ton",
    "$/TON": "short_ton",
}


class UsdaReportRow(BaseModel):
    """One row of a USDA price report, as published.

    Attributes:
        commodity: Commodity label as USDA writes it.
        report_date: Date the report covers.
        avg_price: Average price reported. Required to be present, but may be
            null: a report legitimately publishes no price for a commodity that
            did not trade, whereas a missing field means the payload shape changed
            and should be reported rather than quietly tolerated.
        price_unit: Unit label as USDA writes it.
    """

    model_config = ConfigDict(extra="ignore")

    commodity: str = Field(min_length=1)
    report_date: datetime
    avg_price: Decimal | None
    price_unit: str | None = None

    @field_validator("report_date", mode="before")
    @classmethod
    def _parse_report_date(cls, value: object) -> object:
        """Accept the several date formats USDA uses across reports.

        Args:
            value: Raw date value from the report.

        Returns:
            A parsed datetime, or the value unchanged for pydantic to handle.

        Raises:
            ValueError: If the text matches none of the known formats.
        """
        if not isinstance(value, str):
            return value
        text = value.strip()
        for date_format in _DATE_FORMATS:
            try:
                return datetime.strptime(text, date_format).replace(tzinfo=UTC)
            except ValueError:
                continue
        raise ValueError(f"Unrecognised report date {value!r}")


_ROWS_ADAPTER = TypeAdapter(list[UsdaReportRow])


@default_registry.source(SOURCE_ID)
class UsdaGrainPriceIngestor:
    """Reads bulk grain prices from the USDA Market News API."""

    source_id = SOURCE_ID
    source_name = SOURCE_NAME

    def __init__(self, context: IngestionContext) -> None:
        """Create the ingestor.

        Args:
            context: Shared HTTP client and settings.
        """
        self._http = context.http
        self._settings = context.settings

    @property
    def is_configured(self) -> bool:
        """Whether this source can run.

        Returns:
            True when a USDA API key is present. The key is free but optional, so
            a scheduled run skips this source instead of failing without one.
        """
        return self._settings.usda_mars_api_key is not None

    async def ingest(self) -> IngestionResult:
        """Fetch the latest grain price report and return price records.

        Returns:
            One price per tracked commodity that reported a price. Empty when no
            API key is configured.

        Raises:
            pydantic.ValidationError: If the report does not match the documented
                shape.
        """
        key = self._settings.usda_mars_api_key
        if key is None:
            return IngestionResult(source_name=self.source_name)

        credentials = base64.b64encode(f"{key.get_secret_value()}:".encode()).decode()
        url = f"{ENDPOINT}/{REPORT_SLUG}"
        payload = await self._http.get_json(
            url,
            headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        )

        rows = _ROWS_ADAPTER.validate_python(_unwrap(payload))
        return IngestionResult(
            source_name=self.source_name,
            prices=tuple(self._to_prices(rows, url)),
        )

    def _to_prices(self, rows: list[UsdaReportRow], source_url: str) -> list[CommodityPrice]:
        """Convert report rows into price records.

        Args:
            rows: Validated report rows.
            source_url: Endpoint the rows were read from, stored for attribution.

        Returns:
            One price per usable row of a tracked commodity.
        """
        prices: list[CommodityPrice] = []
        for row in rows:
            tracked = USDA_COMMODITIES.get(row.commodity.strip().upper())
            if tracked is None or row.avg_price is None:
                continue
            prices.append(
                CommodityPrice(
                    entity_name=tracked.entity_name,
                    sector=Sector.AGRICULTURE,
                    price=row.avg_price,
                    currency="USD",
                    unit=_resolve_unit(row.price_unit, tracked.unit),
                    recorded_at=row.report_date,
                    source_name=SOURCE_NAME,
                    source_url=source_url,
                    ingestion_method=IngestionMethod.OFFICIAL_API,
                )
            )
        return prices


def _unwrap(payload: object) -> object:
    """Return the list of rows, whether or not the response wraps them.

    Some report endpoints return a bare list and others return an object with a
    ``results`` key. Both are valid responses from this service.

    Args:
        payload: Decoded response body.

    Returns:
        The value that should be validated as a list of rows.
    """
    if isinstance(payload, dict):
        wrapped: Any = payload.get("results", payload)
        return wrapped
    return payload


def _resolve_unit(reported: str | None, fallback: str) -> str:
    """Translate a USDA unit label into our own vocabulary.

    An unfamiliar label is not a reason to discard a valid price, so the tracked
    default is used instead.

    Args:
        reported: Unit label as published, if any.
        fallback: Unit to use when the label is missing or unrecognised.

    Returns:
        The unit to store.
    """
    if reported is None:
        return fallback
    return _UNIT_LABELS.get(reported.strip().upper(), fallback)
