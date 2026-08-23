"""Henry Hub natural gas spot price from the US Energy Information Administration.

The EIA publishes daily Henry Hub natural gas futures prices as JSON, free and
without anti-bot protection. This module reads the front-month contract (RNGC1),
which is the standard benchmark quoted in energy markets.

Free API key: https://www.eia.gov/opendata/register.php
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.official._percent import percent_change
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.shared import CommodityPrice, IngestionMethod, Sector

ENDPOINT = "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
SOURCE_ID = "eia_natural_gas"
SOURCE_NAME = "eia.gov"
_SERIES = "RNGC1"
_HISTORY_LENGTH = 30
_WEEK = 7


class _Observation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    series: str = Field(min_length=1)
    period: date
    value: Decimal | None = None


class _ResponseBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    data: list[_Observation] = Field(default_factory=list)


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")
    response: _ResponseBody


@default_registry.source(SOURCE_ID)
class EiaNaturalGasIngestor:
    """Reads Henry Hub natural gas futures prices from the EIA API."""

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
        """True when an EIA API key is present."""
        return self._settings.eia_api_key is not None

    async def ingest(self) -> IngestionResult:
        """Fetch recent Henry Hub prices.

        Returns:
            Price records with day-over-day and week-over-week change.
        """
        if self._settings.eia_api_key is None:
            return IngestionResult(source_name=self.source_name)

        payload = await self._http.get_json(
            ENDPOINT,
            params={
                "api_key": self._settings.eia_api_key.get_secret_value(),
                "frequency": "daily",
                "data[0]": "value",
                "facets[series][]": _SERIES,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
                "length": _HISTORY_LENGTH,
            },
        )

        observations = _Response.model_validate(payload).response.data
        usable: dict[date, Decimal] = {
            obs.period: obs.value for obs in observations if obs.value is not None
        }

        prices: list[CommodityPrice] = []
        for period, value in sorted(usable.items(), reverse=True):
            earlier = [d for d in usable if d < period]
            pct_1d = percent_change(value, usable[max(earlier)]) if earlier else None
            cutoff = date.fromordinal(period.toordinal() - _WEEK)
            week_candidates = [d for d in usable if d <= cutoff]
            pct_7d = (
                percent_change(value, usable[max(week_candidates)]) if week_candidates else None
            )

            prices.append(
                CommodityPrice(
                    entity_name="Natural_Gas",
                    sector=Sector.ENERGY,
                    price=value,
                    currency="USD",
                    unit="mmbtu",
                    pct_change_1d=pct_1d,
                    pct_change_7d=pct_7d,
                    recorded_at=datetime.combine(period, datetime.min.time(), tzinfo=UTC),
                    source_name=SOURCE_NAME,
                    source_url=ENDPOINT,
                    ingestion_method=IngestionMethod.OFFICIAL_API,
                )
            )

        return IngestionResult(source_name=self.source_name, prices=tuple(prices))
