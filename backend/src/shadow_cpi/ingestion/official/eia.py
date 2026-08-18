"""Crude oil spot prices from the US Energy Information Administration.

EIA publishes official daily spot prices as JSON, free, with no anti-bot
protection. Where a source like this exists it is always preferred over scraping:
it is faster, it does not break when a website is redesigned, and there is no
question about whether we are allowed to read it.

The API returns a flat list of observations covering several series at once. This
module keeps only the series the platform tracks, converts each observation into a
price record, and computes day-over-day and week-over-week change by comparing
each observation against earlier ones in the same series.

Free API key: https://www.eia.gov/opendata/register.php
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.official._percent import percent_change
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.shared import CommodityPrice, IngestionMethod, Sector

ENDPOINT = "https://api.eia.gov/v2/petroleum/pri/spt/data/"

SOURCE_ID = "eia_petroleum_spot"
SOURCE_NAME = "eia.gov"

# How many days of history to request. A month is enough to compute weekly change
# even across holidays, and small enough to stay a single quick request.
_HISTORY_LENGTH = 30

# Number of days back that "weekly change" compares against.
_WEEK = 7


@dataclass(frozen=True, slots=True)
class TrackedSeries:
    """A series this platform stores.

    Attributes:
        entity_name: Name used in our own data, for example ``WTI_Crude``.
        unit: What one unit of the price refers to.
    """

    entity_name: str
    unit: str


# EIA series identifiers, mapped to how we store them. Adding a benchmark means
# adding a line here; nothing else changes.
EIA_SERIES: dict[str, TrackedSeries] = {
    "RWTC": TrackedSeries(entity_name="WTI_Crude", unit="barrel"),
    "RBRTE": TrackedSeries(entity_name="Brent_Crude", unit="barrel"),
}


class EiaObservation(BaseModel):
    """One published data point, exactly as EIA returns it.

    Validating the raw payload before using it means a change at the source is
    reported as a clear error rather than silently producing wrong prices.

    Attributes:
        series: EIA series identifier, such as ``RWTC``.
        period: Date the price refers to.
        value: The price. EIA sends null on days with no trading, such as public
            holidays, so this is optional and those rows are skipped.
    """

    model_config = ConfigDict(extra="ignore")

    series: str = Field(min_length=1)
    period: date
    value: Decimal | None = None


class EiaResponseBody(BaseModel):
    """The ``response`` object EIA wraps its data in.

    Attributes:
        data: The observations returned.
    """

    model_config = ConfigDict(extra="ignore")

    data: list[EiaObservation] = Field(default_factory=list)


class EiaResponse(BaseModel):
    """The whole response body.

    Attributes:
        response: The wrapper object holding the observations.
    """

    model_config = ConfigDict(extra="ignore")

    response: EiaResponseBody


@default_registry.source(SOURCE_ID)
class EiaPetroleumSpotIngestor:
    """Reads crude oil spot prices from the EIA API."""

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

        The EIA key is free but optional, so a deployment without one is valid.
        A scheduled run skips unconfigured sources rather than failing.

        Returns:
            True when an API key is present.
        """
        return self._settings.eia_api_key is not None

    async def ingest(self) -> IngestionResult:
        """Fetch recent spot prices and return them as price records.

        Returns:
            Price records for every tracked series, including day-over-day and
            week-over-week change where enough history is available. Empty when no
            API key is configured.

        Raises:
            pydantic.ValidationError: If the response does not match the documented
                shape, for example if the service returns an error page.
        """
        if self._settings.eia_api_key is None:
            return IngestionResult(source_name=self.source_name)

        payload = await self._http.get_json(
            ENDPOINT,
            params={
                "api_key": self._settings.eia_api_key.get_secret_value(),
                "frequency": "daily",
                "data[0]": "value",
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": _HISTORY_LENGTH * len(EIA_SERIES),
            },
        )

        observations = EiaResponse.model_validate(payload).response.data
        return IngestionResult(
            source_name=self.source_name,
            prices=tuple(self._to_prices(observations)),
        )

    def _to_prices(self, observations: list[EiaObservation]) -> list[CommodityPrice]:
        """Convert observations into price records.

        Args:
            observations: Validated observations from the API.

        Returns:
            One price per usable observation of a tracked series.
        """
        prices: list[CommodityPrice] = []
        for series_id, tracked in EIA_SERIES.items():
            # Reporting gaps arrive as null and are dropped here, so the change
            # calculations below only ever compare real published prices.
            usable: dict[date, Decimal] = {
                observation.period: observation.value
                for observation in observations
                if observation.series == series_id and observation.value is not None
            }
            for period, value in sorted(usable.items(), reverse=True):
                prices.append(
                    CommodityPrice(
                        entity_name=tracked.entity_name,
                        sector=Sector.ENERGY,
                        price=value,
                        currency="USD",
                        unit=tracked.unit,
                        pct_change_1d=_change_against_previous(usable, period, value),
                        pct_change_7d=_change_against_days_ago(usable, period, value, _WEEK),
                        recorded_at=datetime.combine(period, datetime.min.time(), tzinfo=UTC),
                        source_name=SOURCE_NAME,
                        source_url=ENDPOINT,
                        ingestion_method=IngestionMethod.OFFICIAL_API,
                    )
                )
        return prices


def _change_against_previous(
    series: Mapping[date, Decimal],
    period: date,
    value: Decimal,
) -> Decimal | None:
    """Compare a price with the previous published price in the same series.

    The previous published price is used rather than "yesterday", because markets
    do not publish at weekends or on holidays.

    Args:
        series: Published prices for one series, keyed by date.
        period: Date of the price being compared.
        value: The price being compared.

    Returns:
        The change in percent, or None when there is no earlier price.
    """
    earlier = [date_key for date_key in series if date_key < period]
    if not earlier:
        return None
    return percent_change(value, series[max(earlier)])


def _change_against_days_ago(
    series: Mapping[date, Decimal],
    period: date,
    value: Decimal,
    days: int,
) -> Decimal | None:
    """Compare a price with the closest published price at least ``days`` earlier.

    Args:
        series: Published prices for one series, keyed by date.
        period: Date of the price being compared.
        value: The price being compared.
        days: How many days back to look.

    Returns:
        The change in percent, or None when history does not reach back far enough.
    """
    cutoff = date.fromordinal(period.toordinal() - days)
    candidates = [date_key for date_key in series if date_key <= cutoff]
    if not candidates:
        return None
    return percent_change(value, series[max(candidates)])
