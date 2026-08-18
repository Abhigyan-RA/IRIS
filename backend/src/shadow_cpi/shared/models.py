"""The three record types this platform stores.

Every data source, whether an official API or a scraped page, is turned into one
of these models before anything else touches it. That is the point: downstream
code, the API, and the dashboard all deal with one shape rather than ten.

The rules here are deliberately strict, and they reject bad input rather than
fixing it. Quietly correcting a value is how a wrong number ends up on a
dashboard with no trace of where it came from.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shadow_cpi.shared.enums import IngestionMethod, PipelineEventType, Sector
from shadow_cpi.shared.validation import normalize_cik, require_utc

# Matches the DECIMAL(14, 4) column that stores prices: at most 14 total digits,
# 4 of them after the decimal point. Validating here means an out-of-range value
# is reported with a clear message instead of a database error.
PriceDecimal = Annotated[Decimal, Field(max_digits=14, decimal_places=4)]

# Matches DECIMAL(6, 3): percentage changes such as -12.345.
PercentDecimal = Annotated[Decimal, Field(max_digits=6, decimal_places=3)]

# A unit of measure such as metric_ton, barrel, feu, index_point, or lb. New
# units are added by using them, but they must look like identifiers so that a
# malformed scrape cannot smuggle punctuation into a stored field.
UnitString = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")]

# ISO 4217 currency code, upper case, exactly three letters.
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]

# Stock ticker: upper-case letters with the dots and dashes some symbols use.
TickerSymbol = Annotated[str, Field(min_length=1, max_length=10, pattern=r"^[A-Z][A-Z.\-]*$")]


class _StrictModel(BaseModel):
    """Base for all records: frozen, no unknown fields, no silent coercion.

    Immutability matters because these objects travel from ingestion to storage
    to the API. If any layer could edit them in place, tracing where a value
    changed would mean reading every layer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class CommodityPrice(_StrictModel):
    """One observed price for one tracked thing at one point in time.

    Attributes:
        entity_name: What was priced, for example ``Copper``, ``Steel_HRC_US``, or
            the freight lane index ``FBX01``.
        sector: Which of the four tracked categories this belongs to.
        price: The observed price. Negative values are allowed on purpose:
            commodities can and do trade below zero.
        currency: Currency of the price, as a three-letter code.
        unit: What one unit of the price refers to, such as ``barrel`` or ``feu``
            (a forty-foot shipping container).
        pct_change_1d: Change since the previous day, in percent, when the source
            publishes it.
        pct_change_7d: Change over the past week, in percent, when available.
        recorded_at: When the price was observed, in UTC.
        source_name: Human-readable source, for example ``investing.com``.
        source_url: Exact page or endpoint the value came from, so any number on
            the dashboard can be checked against its origin.
        ingestion_method: Whether this came from an official API or a scrape.
    """

    entity_name: str = Field(min_length=1, max_length=255)
    sector: Sector
    price: PriceDecimal
    currency: CurrencyCode
    unit: UnitString
    pct_change_1d: PercentDecimal | None = None
    pct_change_7d: PercentDecimal | None = None
    recorded_at: datetime
    source_name: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1)
    ingestion_method: IngestionMethod

    @field_validator("recorded_at")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        """Require a timezone and store the moment in UTC.

        Args:
            value: Timestamp as provided by the source.

        Returns:
            The same moment expressed in UTC.
        """
        return require_utc(value)

    @field_validator("source_url")
    @classmethod
    def _require_web_url(cls, value: str) -> str:
        """Require an ``http`` or ``https`` source URL.

        The URL is rendered as a link in the dashboard, so accepting other
        schemes would let a scraped page inject something executable.

        Args:
            value: URL as provided by the source.

        Returns:
            The validated URL.

        Raises:
            ValueError: If the URL is not an HTTP or HTTPS address.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("source_url must start with http:// or https://")
        return value


MarketValue = Annotated[Decimal, Field(max_digits=18, decimal_places=2, ge=0)]
PortfolioPercent = Annotated[Decimal, Field(max_digits=6, decimal_places=3, ge=0, le=100)]


class InstitutionalHolding(_StrictModel):
    """One position held by one investment manager at the end of one quarter.

    Managers overseeing more than 100 million dollars must disclose their US
    equity positions to the SEC every quarter. This model is one line of one such
    disclosure.

    Attributes:
        filer_name: Name of the investment manager.
        filer_cik: The manager's ten-digit SEC identifier.
        stock_ticker: Ticker symbol of the holding.
        shares_held: Number of shares held at quarter end. Never negative:
            short positions are not reported on this form.
        market_value_usd: Reported value of the position in US dollars.
        pct_portfolio: Share of the manager's reported portfolio, in percent.
        shares_change_qoq: Change in share count since the previous quarter.
            Negative when the manager reduced the position.
        quarter_end: Last day of the quarter being reported.
        source_url: Where this line was read from.
    """

    filer_name: str = Field(min_length=1, max_length=255)
    filer_cik: str
    stock_ticker: TickerSymbol
    shares_held: int = Field(ge=0)
    market_value_usd: MarketValue | None = None
    pct_portfolio: PortfolioPercent | None = None
    shares_change_qoq: int | None = None
    quarter_end: date
    source_url: str | None = None

    @field_validator("filer_cik")
    @classmethod
    def _normalize_filer_cik(cls, value: str) -> str:
        """Store the filer identifier in its canonical ten-digit form.

        Args:
            value: CIK in any of the forms sources publish.

        Returns:
            The ten-digit CIK.
        """
        return normalize_cik(value)


class PipelineHealthEvent(_StrictModel):
    """Something that happened to a collector, as shown in the health feed.

    These events are what make the pipeline observable: they are the difference
    between "the dashboard looks stale" and "this scraper broke at 03:00, repaired
    itself at 03:02, and resumed at 03:03".

    Attributes:
        scraper_id: Identifier of the collector, for example
            ``whalewisdom_13f_scraper``.
        source_name: Website or API the collector targets.
        event_type: Which stage of the run this event represents.
        message: Human-readable detail, using text labels such as ``[WARNING]``
            and ``[RESOLVED]`` rather than emoji.
        occurred_at: When it happened, in UTC.
    """

    scraper_id: str = Field(min_length=1, max_length=100)
    source_name: str = Field(min_length=1, max_length=100)
    event_type: PipelineEventType
    message: str | None = None
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        """Require a timezone and store the moment in UTC.

        Args:
            value: Timestamp of the event.

        Returns:
            The same moment expressed in UTC.
        """
        return require_utc(value)
