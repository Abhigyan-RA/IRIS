"""Turning messy scraped payloads into price records.

Scraped pages are written for people. Prices arrive as ``$4.52``, ``4,520.75``, or
``USD 4.52 / lb``, under headings that differ from one site to the next and change
without notice. Simple parsing handles the common cases; this handles the rest by
asking the model to restate a payload in one fixed shape.

Two safeguards make that safe to rely on. The model's answer is validated against
the same strict record used everywhere else, so a wrong shape or an impossible
currency is rejected rather than stored. And a failure returns nothing instead of
raising, because one unreadable payload must not abort a run that still has other
sources to collect.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, ValidationError

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.ai.prompts import NORMALIZE_SYSTEM, NORMALIZE_USER
from shadow_cpi.ai.protocols import StructuredModel
from shadow_cpi.ingestion.brightdata.collectors import ScrapedSource
from shadow_cpi.shared import CommodityPrice, IngestionMethod


class NormalizedPrice(BaseModel):
    """The shape the model is asked to return.

    Deliberately smaller than the stored record: the model is only asked for what
    it can read off the page. Everything else, including where the value came from
    and when it was read, is known by the collector and added afterwards, so the
    model can neither guess nor corrupt it.

    Attributes:
        entity_name: What was priced.
        price: The price, or None when the page shows no usable value.
        currency: Three-letter currency code.
        unit: What one unit refers to.
        pct_change_1d: Change since the previous day, in percent, when shown.
    """

    model_config = ConfigDict(extra="ignore")

    entity_name: str
    price: Decimal | None
    currency: str
    unit: str
    pct_change_1d: Decimal | None = None


class GeminiPriceNormalizer:
    """Restates a scraped payload as a price record."""

    def __init__(self, model: StructuredModel) -> None:
        """Create the normalizer.

        Args:
            model: The model to ask, injected so tests script its replies.
        """
        self._model = model

    async def normalize(
        self,
        raw_payload: object,
        source: ScrapedSource,
        observed_at: datetime,
    ) -> CommodityPrice | None:
        """Convert one scraped payload into a price record.

        Args:
            raw_payload: Whatever the collector returned, in whatever shape.
            source: Description of the page it came from, which supplies the
                category, units, and attribution.
            observed_at: When the page was read. A scraped page shows a live value
                without saying when it was published, so the read time is the only
                honest timestamp available.

        Returns:
            The price record, or None when the payload holds no usable price or the
            model could not produce a valid one.
        """
        prompt = NORMALIZE_USER.format(
            payload=json.dumps(raw_payload, default=str)[:4000],
            entity_name=source.entity_name,
        )

        try:
            extracted = await self._model.generate_model(NORMALIZE_SYSTEM, prompt, NormalizedPrice)
        except (GeminiError, ValidationError, json.JSONDecodeError):
            return None

        if extracted.price is None:
            return None

        try:
            return CommodityPrice(
                entity_name=source.entity_name,
                sector=source.sector,
                price=extracted.price,
                currency=extracted.currency,
                unit=extracted.unit or source.unit,
                pct_change_1d=extracted.pct_change_1d,
                recorded_at=observed_at,
                source_name=source.source_name,
                source_url=source.url,
                ingestion_method=IngestionMethod.BRIGHTDATA_SCRAPE,
            )
        except ValidationError:
            # The model returned something the record refuses, such as a currency
            # spelled out in words. Rejecting it is the point of validating.
            return None
