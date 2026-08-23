"""WhaleWisdom's public filer pages as a bounded institutional enrichment source.

The official SEC ingestor is the production holdings ledger. This source deliberately writes
only fund summaries and human-readable metadata that the public WhaleWisdom UI adds. It never
writes shares or market values into the official table, so a commercial page or a repaired
scraper cannot replace a regulator-sourced fact.

Coverage is a configured watchlist, not a site crawl. WhaleWisdom's licensed API is the correct
route for exhaustive commercial use; the public-page collector exists for the self-healing demo
path described by the product architecture.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from pydantic import ValidationError

from shadow_cpi.ingestion.base import IngestionContext, IngestionResult
from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome
from shadow_cpi.ingestion.brightdata.studio import ScraperStudioClient
from shadow_cpi.ingestion.brightdata.studio_runner import SelfHealingStudioRunner
from shadow_cpi.ingestion.registry import default_registry
from shadow_cpi.shared import (
    InstitutionalFundSnapshot,
    InstitutionalHoldingEnrichment,
    PipelineHealthEvent,
)

logger = logging.getLogger(__name__)

WHALEWISDOM_SOURCE_ID = "whalewisdom_13f_scraper"
SOURCE_NAME = "whalewisdom.com"
_REQUIRED_PATHS = ()
_TICKER = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
_COUNT = re.compile(r"\bof\s+([\d,]+)\b", re.IGNORECASE)
_PRIOR = re.compile(r",\s*prior\b", re.IGNORECASE)
_NUMBER = re.compile(r"[-+]?\(?[\d,.]+\)?")
_MULTIPLIER = {"k": Decimal(1_000), "m": Decimal(1_000_000), "b": Decimal(1_000_000_000)}


@dataclass(frozen=True, slots=True)
class WhaleWisdomFund:
    """One explicitly configured public filer page."""

    cik: str
    name: str
    slug: str

    @property
    def url(self) -> str:
        """Exact holdings tab to collect."""
        return f"https://whalewisdom.com/filer/{self.slug}"


# The watchlist is deliberately explicit. Every identifier here is one the official SEC
# ingestor already tracks, so enrichment can only ever describe a fund whose filings are
# the authoritative record. Names and identifiers match that official list exactly,
# because enrichment is joined to official rows by identifier and quarter.
DEFAULT_WHALEWISDOM_FUNDS: tuple[WhaleWisdomFund, ...] = (
    WhaleWisdomFund("0001350694", "Bridgewater Associates", "bridgewater-associates-inc"),
    WhaleWisdomFund("0000093751", "State Street Corp", "state-street-corp"),
    WhaleWisdomFund("0001067983", "Berkshire Hathaway", "berkshire-hathaway-inc"),
    WhaleWisdomFund("0000895421", "Millennium Management LLC", "millennium-management-l-l-c"),
    WhaleWisdomFund("0000070858", "Northern Trust Corp", "northern-trust-corp"),
    WhaleWisdomFund("0000914208", "Invesco Ltd", "invesco-plc-london"),
    WhaleWisdomFund(
        "0000315066",
        "Fidelity Management & Research Company LLC",
        "fidelity-management-amp-research-co-ma",
    ),
    WhaleWisdomFund(
        "0000019617",
        "T Rowe Price Associates Inc",
        "price-t-rowe-associates-inc-md",
    ),
    WhaleWisdomFund("0000038777", "Franklin Resources Inc", "franklin-resources-inc"),
    WhaleWisdomFund("0001418814", "D E Shaw & Co Inc", "d-e-shaw-co-inc"),
    WhaleWisdomFund("0001061768", "Point72 Asset Management LP", "point72-asset-management-lp"),
)


class WhaleRunner(Protocol):
    """Runs one configured page through the self-healing collector."""

    async def run(self, collector_id: str, source_name: str, url: str) -> RunOutcome:
        """Return the collector rows or an empty failed outcome."""
        ...


class _DiscardingEvents:
    async def record_event(self, event: PipelineHealthEvent) -> None:
        """Discard an event only when a source is exercised outside a real run."""


class _WhaleRepairInstruction:
    """Keep repair instructions semantic and explicitly scoped to one input page."""

    async def draft(
        self,
        collector_id: str,
        missing_fields: Sequence[str],
        reason: str,
    ) -> str:
        fields = ", ".join(missing_fields) or "quarter and holdings"
        return (
            f"On only the supplied input filer page, restore {fields}. Read the report quarter, "
            "total reported market value, and visible holding rows with name, ticker, shares, "
            "market value, portfolio percent, share change, and percent change. Do not discover "
            "other filer URLs, paginate, or infer missing values."
        )


@default_registry.source(WHALEWISDOM_SOURCE_ID)
class WhaleWisdomIngestor:
    """Collect a configured fund watchlist through one reusable Studio collector."""

    source_id = WHALEWISDOM_SOURCE_ID
    source_name = SOURCE_NAME

    def __init__(
        self,
        context: IngestionContext,
        runner: WhaleRunner | None = None,
        funds: tuple[WhaleWisdomFund, ...] = DEFAULT_WHALEWISDOM_FUNDS,
    ) -> None:
        """Create the bounded watchlist ingestor and its self-healing runner."""
        self._collector_id = context.settings.collector_for(self.source_id)
        self._funds = funds
        sink = context.events or _DiscardingEvents()
        self._runner = runner or SelfHealingStudioRunner(
            api=ScraperStudioClient(
                http=context.http,
                api_key=context.settings.brightdata_api_key.get_secret_value(),
            ),
            events=sink,
            drafter=_WhaleRepairInstruction(),
            auto_approve_repairs=context.settings.brightdata_auto_approve_heal,
            required_fields=_REQUIRED_PATHS,
        )

    @property
    def is_configured(self) -> bool:
        """Whether a Studio collector is registered for this source."""
        return self._collector_id is not None

    async def ingest(self) -> IngestionResult:
        """Collect every configured fund, isolating one failed page from the others."""
        if self._collector_id is None:
            return IngestionResult(source_name=self.source_name)

        snapshots: list[InstitutionalFundSnapshot] = []
        enrichments: list[InstitutionalHoldingEnrichment] = []
        observed_at = datetime.now(UTC)

        for fund in self._funds:
            outcome = await self._runner.run(self._collector_id, self.source_name, fund.url)
            if not outcome.rows:
                logger.warning(
                    "%s returned no usable rows for %s (%s)",
                    self.source_name,
                    fund.name,
                    outcome.reason,
                )
                continue

            for row in outcome.rows:
                parsed = _parse_result(row, fund, observed_at)
                if parsed is None:
                    continue
                snapshot, fund_enrichments = parsed
                snapshots.append(snapshot)
                enrichments.extend(fund_enrichments)

        return IngestionResult(
            source_name=self.source_name,
            fund_snapshots=tuple(snapshots),
            holding_enrichments=tuple(enrichments),
        )


def _parse_result(
    row: Mapping[str, object],
    fund: WhaleWisdomFund,
    observed_at: datetime,
) -> tuple[InstitutionalFundSnapshot, list[InstitutionalHoldingEnrichment]] | None:
    """Map one collected page to a snapshot and its holding metadata.

    Every value is read from the page. Nothing is inferred: a page that does not state
    its quarter, or carries no holding rows, is reported as unusable rather than filled
    in with a guess.

    Args:
        row: One collected result object.
        fund: The configured filer the page belongs to.
        observed_at: When the page was read.

    Returns:
        The snapshot and its enrichment rows, or None when the page is unusable.
    """
    quarter = _date(row.get("quarter"))
    holdings = row.get("holdings")
    raw_holdings = holdings if isinstance(holdings, list) else []

    if quarter is None or not raw_holdings:
        return None

    try:
        snapshot = InstitutionalFundSnapshot(
            filer_name=fund.name,
            filer_cik=fund.cik,
            report_period=quarter,
            reported_value_usd=_money(row.get("total_holdings")),
            holdings_count=_count(row.get("holdings_count")),
            source_url=fund.url,
            observed_at=observed_at,
        )
    except ValidationError:
        logger.warning("%s page for %s did not validate", SOURCE_NAME, fund.name)
        return None

    enrichments: list[InstitutionalHoldingEnrichment] = []
    for rank, item in enumerate(raw_holdings, start=1):
        if not isinstance(item, Mapping):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if not _TICKER.fullmatch(ticker):
            continue
        try:
            enrichments.append(
                InstitutionalHoldingEnrichment(
                    filer_cik=fund.cik,
                    stock_ticker=ticker,
                    quarter_end=quarter,
                    stock_name=_text(item.get("name")),
                    sector=_text(item.get("sector")),
                    previous_pct_portfolio=_decimal(item.get("previous_percent_of_portfolio")),
                    rank=rank,
                    reported_pct_change_shares=_decimal(item.get("change_in_shares")),
                    source_url=fund.url,
                    observed_at=observed_at,
                )
            )
        except ValidationError:
            logger.debug("skipping unusable holding row for %s", ticker)
            continue

    return snapshot, enrichments


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _count(value: object) -> int | None:
    if isinstance(value, int):
        return value if value >= 0 else None
    text = str(value or "")
    matched = _COUNT.search(text)
    candidate = matched.group(1) if matched else text
    digits = candidate.replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = str(value or "").strip()
    if not text or text.lower() in {"new", "sold all", "n/a", "--"}:
        return None
    matched = _NUMBER.search(text.replace("$", "").replace("%", ""))
    if matched is None:
        return None
    raw = matched.group(0).replace(",", "")
    negative = raw.startswith("(") and raw.endswith(")")
    try:
        number = Decimal(raw.strip("()"))
    except InvalidOperation:
        return None
    return -number if negative else number


def _money(value: object) -> Decimal | None:
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    # A fund page states the current total and often the previous one beside it, as
    # "$20.2b, Prior: $13.7b". Only the current figure is stored. Splitting on the
    # comma itself would break a plain grouped number such as "5,673,738,513".
    head = _PRIOR.split(str(value or ""), maxsplit=1)[0].strip().lower()
    if not head:
        return None

    suffix = head[-1:] if head[-1:] in _MULTIPLIER else ""
    number = _decimal(head[:-1] if suffix else head)
    if number is None:
        return None

    return number * _MULTIPLIER.get(suffix, Decimal(1))
