"""Institutional holdings endpoints.

These answer "what did the professional money do this quarter", which is a second,
independent signal alongside the raw prices: a commodity moving is one thing, funds
positioning for it is another.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from shadow_cpi.api.dependencies import require_holdings, require_institutional
from shadow_cpi.db.protocols import HoldingsReader, InstitutionalIntelligenceReader
from shadow_cpi.shared import (
    InstitutionalFundSnapshot,
    InstitutionalHolding,
    InstitutionalHoldingEnrichment,
    normalize_cik,
)

_PERCENT_PRECISION = Decimal("0.001")

router = APIRouter(prefix="/api/institutional", tags=["institutional"])


class HolderEntry(BaseModel):
    """One fund's position in a stock.

    Attributes:
        filer_name: Name of the fund.
        filer_cik: The fund's identifier.
        shares_held: Shares held at quarter end.
        market_value_usd: Reported value of the position.
        pct_portfolio: Share of the fund's reported portfolio, in percent.
        shares_change_qoq: Change in share count since the previous quarter.
        delta_pct: That change as a percentage of the previous quarter's holding,
            which is the figure people actually quote.
        quarter_end: Quarter the disclosure covers.
        source_url: Filing the numbers came from.
    """

    filer_name: str
    filer_cik: str
    shares_held: int
    market_value_usd: Decimal | None
    pct_portfolio: Decimal | None
    shares_change_qoq: int | None
    delta_pct: Decimal | None
    quarter_end: date
    source_url: str | None


class HoldersResponse(BaseModel):
    """Every fund reporting a position in one stock.

    Attributes:
        ticker: The stock, as stored.
        holders: The positions, largest first.
    """

    ticker: str
    holders: list[HolderEntry]


class HoldingEntry(BaseModel):
    """One position in a fund's portfolio.

    Attributes:
        stock_ticker: The stock held.
        shares_held: Shares held at quarter end.
        market_value_usd: Reported value of the position.
        pct_portfolio: Share of the fund's reported portfolio, in percent.
        shares_change_qoq: Change in share count since the previous quarter.
        delta_pct: That change as a percentage of the previous quarter's holding.
        quarter_end: Quarter the disclosure covers.
        source_url: Filing the numbers came from.
        sector: GICS sector from WhaleWisdom enrichment, when available.
        rank: Portfolio rank from WhaleWisdom enrichment, when available.
        previous_pct_portfolio: Prior quarter portfolio weight, when available.
    """

    stock_ticker: str
    shares_held: int
    market_value_usd: Decimal | None
    pct_portfolio: Decimal | None
    shares_change_qoq: int | None
    delta_pct: Decimal | None
    quarter_end: date
    source_url: str | None
    sector: str | None = None
    rank: int | None = None
    previous_pct_portfolio: Decimal | None = None


class FilerHoldingsResponse(BaseModel):
    """One fund's reported portfolio.

    Attributes:
        filer_cik: The fund's identifier.
        filer_name: The fund's name, or None when it has filed nothing we hold.
        holdings: The positions, largest first.
    """

    filer_cik: str
    filer_name: str | None
    holdings: list[HoldingEntry]


def _delta_pct(holding: InstitutionalHolding) -> Decimal | None:
    """Express a quarter-over-quarter change as a percentage.

    The stored figure is a change in share count. The percentage is derived from
    the previous quarter's holding, which is what "increased its position 14
    percent" means.

    Args:
        holding: The position.

    Returns:
        The change in percent, or None for a brand-new position, where there is
        nothing to compare against. A new position is not a zero-percent change.
    """
    change = holding.shares_change_qoq
    if change is None:
        return None
    previous = holding.shares_held - change
    if previous <= 0:
        return None
    return (Decimal(change) / Decimal(previous) * Decimal(100)).quantize(
        _PERCENT_PRECISION, rounding=ROUND_HALF_UP
    )


def _by_size(holding: InstitutionalHolding) -> Decimal:
    """Return a position's reported value for sorting.

    Args:
        holding: The position.

    Returns:
        The value, or zero when none was reported.
    """
    return holding.market_value_usd or Decimal(0)


@router.get(
    "/holders/{ticker}",
    response_model=HoldersResponse,
    summary="Funds holding one stock",
)
async def read_holders(
    holdings: Annotated[HoldingsReader, Depends(require_holdings)],
    ticker: Annotated[str, Path(min_length=1, max_length=10, pattern=r"^[A-Za-z][A-Za-z.\-]*$")],
    quarter_end: Annotated[date | None, Query()] = None,
) -> HoldersResponse:
    """Return the funds reporting a position in one stock.

    Args:
        holdings: Holdings store to read from.
        ticker: Ticker symbol. Case is normalized by the store.
        quarter_end: Restrict to one quarter, or omit for every quarter held.

    Returns:
        The positions, largest first. A stock nobody reported returns an empty
        list, which is an answer rather than an error.
    """
    rows = await holdings.holders_of(ticker, quarter_end)
    ordered = sorted(rows, key=_by_size, reverse=True)
    return HoldersResponse(
        ticker=ticker.upper(),
        holders=[
            HolderEntry(
                filer_name=row.filer_name,
                filer_cik=row.filer_cik,
                shares_held=row.shares_held,
                market_value_usd=row.market_value_usd,
                pct_portfolio=row.pct_portfolio,
                shares_change_qoq=row.shares_change_qoq,
                delta_pct=_delta_pct(row),
                quarter_end=row.quarter_end,
                source_url=row.source_url,
            )
            for row in ordered
        ],
    )


@router.get(
    "/filer/{filer_cik}/holdings",
    response_model=FilerHoldingsResponse,
    summary="One fund's reported portfolio",
)
async def read_filer_holdings(
    holdings: Annotated[HoldingsReader, Depends(require_holdings)],
    institutional: Annotated[InstitutionalIntelligenceReader, Depends(require_institutional)],
    filer_cik: Annotated[str, Path(min_length=1, max_length=20)],
    quarter_end: Annotated[date | None, Query()] = None,
) -> FilerHoldingsResponse:
    """Return one fund's reported positions, enriched with sector and rank.

    Args:
        holdings: Holdings store to read from.
        institutional: Enrichment store for sector and rank data.
        filer_cik: The fund's identifier, in any of the forms it is written in.
        quarter_end: Restrict to one quarter, or omit for every quarter held.

    Returns:
        The positions, largest first, with sector and rank joined from enrichments.

    Raises:
        HTTPException: If the identifier is not a valid fund identifier.
    """
    try:
        normalized = normalize_cik(filer_cik)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    rows = await holdings.holdings_of_filer(filer_cik, quarter_end)
    ordered = sorted(rows, key=_by_size, reverse=True)

    # Build an enrichment lookup keyed by ticker for the relevant quarter.
    # rows is already filtered by quarter when quarter_end is supplied; when it is
    # not, derive the newest quarter from the returned rows without passing None to
    # max(), which mypy rejects as an incompatible default type.
    if quarter_end:
        effective_quarter: date | None = quarter_end
    else:
        quarters = [r.quarter_end for r in rows]
        effective_quarter = max(quarters) if quarters else None
    all_enrichments = await institutional.latest_holding_enrichments()
    enrichment_map = {
        e.stock_ticker: e
        for e in all_enrichments
        if e.filer_cik == normalized
        and (effective_quarter is None or e.quarter_end == effective_quarter)
    }

    return FilerHoldingsResponse(
        filer_cik=normalized,
        filer_name=ordered[0].filer_name if ordered else None,
        holdings=[
            HoldingEntry(
                stock_ticker=row.stock_ticker,
                shares_held=row.shares_held,
                market_value_usd=row.market_value_usd,
                pct_portfolio=row.pct_portfolio,
                shares_change_qoq=row.shares_change_qoq,
                delta_pct=_delta_pct(row),
                quarter_end=row.quarter_end,
                source_url=row.source_url,
                sector=(
                    enrichment_map[row.stock_ticker].sector
                    if row.stock_ticker in enrichment_map
                    else None
                ),
                rank=(
                    enrichment_map[row.stock_ticker].rank
                    if row.stock_ticker in enrichment_map
                    else None
                ),
                previous_pct_portfolio=(
                    enrichment_map[row.stock_ticker].previous_pct_portfolio
                    if row.stock_ticker in enrichment_map
                    else None
                ),
            )
            for row in ordered
        ],
    )


class FundEnrichmentEntry(BaseModel):
    """Public fund-page fields stored separately from the official ledger."""

    report_period: date
    filing_date: date | None
    reported_value_usd: Decimal | None
    discretionary_aum_usd: Decimal | None
    top_10_concentration_pct: Decimal | None
    holdings_count: int | None
    portfolio_turnover_pct: Decimal | None
    whale_score: Decimal | None
    net_share_change: int | None
    source_name: str
    source_url: str
    observed_at: datetime


class FundSummaryEntry(BaseModel):
    """One manager aggregated from official latest-quarter positions."""

    filer_name: str
    filer_cik: str
    position_count: int
    reported_value_usd: Decimal
    source_name: str = "SEC EDGAR"
    source_url: str | None
    enrichment: FundEnrichmentEntry | None


class StockSummaryEntry(BaseModel):
    """One stock aggregated across every current manager in storage."""

    stock_ticker: str
    stock_name: str | None
    sector: str | None
    holder_count: int
    shares_held: int
    market_value_usd: Decimal
    shares_change_qoq: int
    enriched_positions: int


class InstitutionalMoveEntry(BaseModel):
    """One official position ranked by reported share-count change."""

    filer_name: str
    filer_cik: str
    stock_ticker: str
    shares_held: int
    market_value_usd: Decimal | None
    shares_change_qoq: int
    quarter_end: date
    source_name: str = "SEC EDGAR"
    source_url: str | None


class EnrichmentOnlyFundEntry(BaseModel):
    """A watchlist fund with public-page data but no official filing stored.

    Kept in its own list rather than mixed into the official funds, so a scraped
    figure is never mistaken for a filed one. Values here come from the public page.
    """

    filer_name: str
    filer_cik: str
    holdings_count: int | None
    reported_value_usd: Decimal | None
    source_name: str
    source_url: str
    observed_at: datetime


class EnrichmentCoverage(BaseModel):
    """How much of the official current ledger has matching public-page metadata.

    Attributes:
        matched_funds: Watchlist funds that also have official positions stored.
        enrichment_only_funds: Watchlist funds with no official filing stored.
        matched_positions: Enrichment rows that join to an official position.
        observed_at: Newest enrichment observation used.
    """

    matched_funds: int
    enrichment_only_funds: int
    matched_positions: int
    observed_at: datetime | None


class InstitutionalOverviewResponse(BaseModel):
    """Bounded current-quarter institutional intelligence response."""

    quarter_end: date | None
    total_funds: int
    total_stocks: int
    total_positions: int
    funds: list[FundSummaryEntry]
    enrichment_only_funds: list[EnrichmentOnlyFundEntry]
    stocks: list[StockSummaryEntry]
    top_buys: list[InstitutionalMoveEntry]
    top_sells: list[InstitutionalMoveEntry]
    enrichment_coverage: EnrichmentCoverage
    coverage_note: str


_COVERAGE_NOTE = (
    "Official SEC 13F coverage includes every latest-quarter position currently stored; "
    "human-readable enrichment is limited to the configured WhaleWisdom watchlist. "
    "Watchlist funds listed separately have no official filing stored yet, so their "
    "figures come from the public page rather than a filing, and they are excluded from "
    "the official totals. "
    "13F reports are quarterly, delayed, long-only disclosures and do not show shorts."
)


def _fund_enrichment(
    snapshot: InstitutionalFundSnapshot,
    enrichments: list[InstitutionalHoldingEnrichment],
) -> FundEnrichmentEntry:
    net = sum(
        int(e.reported_pct_change_shares)
        for e in enrichments
        if e.reported_pct_change_shares is not None
    )
    return FundEnrichmentEntry(
        report_period=snapshot.report_period,
        filing_date=snapshot.filing_date,
        reported_value_usd=snapshot.reported_value_usd,
        discretionary_aum_usd=snapshot.discretionary_aum_usd,
        top_10_concentration_pct=snapshot.top_10_concentration_pct,
        holdings_count=snapshot.holdings_count,
        portfolio_turnover_pct=snapshot.portfolio_turnover_pct,
        whale_score=snapshot.whale_score,
        net_share_change=net if enrichments else None,
        source_name=snapshot.source_name,
        source_url=snapshot.source_url,
        observed_at=snapshot.observed_at,
    )


def _move(holding: InstitutionalHolding) -> InstitutionalMoveEntry:
    change = holding.shares_change_qoq
    if change is None:  # guarded by the caller; retained for type narrowing safety
        raise ValueError("a ranked move requires shares_change_qoq")
    return InstitutionalMoveEntry(
        filer_name=holding.filer_name,
        filer_cik=holding.filer_cik,
        stock_ticker=holding.stock_ticker,
        shares_held=holding.shares_held,
        market_value_usd=holding.market_value_usd,
        shares_change_qoq=change,
        quarter_end=holding.quarter_end,
        source_url=holding.source_url,
    )


@router.get(
    "/overview",
    response_model=InstitutionalOverviewResponse,
    summary="Current institutional holdings and public-page enrichment",
)
async def read_institutional_overview(
    institutional: Annotated[InstitutionalIntelligenceReader, Depends(require_institutional)],
    fund_limit: Annotated[int, Query(ge=1, le=1000)] = 250,
    stock_limit: Annotated[int, Query(ge=1, le=1000)] = 250,
    mover_limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InstitutionalOverviewResponse:
    """Aggregate the latest official quarter and join bounded watchlist enrichment."""
    holdings = await institutional.latest_holdings()
    snapshots = await institutional.latest_fund_snapshots()
    enrichments = await institutional.latest_holding_enrichments()
    # Prefer the newest official quarter. When nothing official is stored yet, fall back
    # to the newest enriched period so collected watchlist data is still reported rather
    # than silently dropped.
    quarter_end = max((row.quarter_end for row in holdings), default=None) or max(
        (row.report_period for row in snapshots), default=None
    )
    current = [row for row in holdings if row.quarter_end == quarter_end]

    matching_snapshots = {
        row.filer_cik: row
        for row in snapshots
        if quarter_end is not None and row.report_period == quarter_end
    }
    matching_enrichments: dict[tuple[str, str], InstitutionalHoldingEnrichment] = {
        (row.filer_cik, row.stock_ticker): row
        for row in enrichments
        if quarter_end is not None and row.quarter_end == quarter_end
    }

    fund_rows: dict[str, list[InstitutionalHolding]] = {}
    stock_rows: dict[str, list[InstitutionalHolding]] = {}
    official_positions: set[tuple[str, str]] = set()
    for row in current:
        fund_rows.setdefault(row.filer_cik, []).append(row)
        stock_rows.setdefault(row.stock_ticker, []).append(row)
        official_positions.add((row.filer_cik, row.stock_ticker))

    # Group enrichments by fund so net_share_change can be computed per fund.
    enrichments_by_fund: dict[str, list[InstitutionalHoldingEnrichment]] = {}
    for enr in matching_enrichments.values():
        enrichments_by_fund.setdefault(enr.filer_cik, []).append(enr)

    funds = [
        FundSummaryEntry(
            filer_name=rows[0].filer_name,
            filer_cik=cik,
            position_count=len(rows),
            reported_value_usd=sum(
                (row.market_value_usd or Decimal(0) for row in rows), Decimal(0)
            ),
            source_url=rows[0].source_url,
            enrichment=(
                _fund_enrichment(
                    matching_snapshots[cik],
                    enrichments_by_fund.get(cik, []),
                )
                if cik in matching_snapshots
                else None
            ),
        )
        for cik, rows in fund_rows.items()
    ]
    funds.sort(key=lambda row: row.reported_value_usd, reverse=True)

    # A watchlist fund with no official filing stored is reported on its own, so it is
    # visible without its scraped value entering an official total.
    enrichment_only = [
        EnrichmentOnlyFundEntry(
            filer_name=snapshot.filer_name,
            filer_cik=cik,
            holdings_count=snapshot.holdings_count,
            reported_value_usd=snapshot.reported_value_usd,
            source_name=snapshot.source_name,
            source_url=snapshot.source_url,
            observed_at=snapshot.observed_at,
        )
        for cik, snapshot in matching_snapshots.items()
        if cik not in fund_rows
    ]
    enrichment_only.sort(
        key=lambda row: row.reported_value_usd or Decimal(0),
        reverse=True,
    )

    stocks: list[StockSummaryEntry] = []
    for ticker, rows in stock_rows.items():
        matched = [
            matching_enrichments[(row.filer_cik, ticker)]
            for row in rows
            if (row.filer_cik, ticker) in matching_enrichments
        ]
        stocks.append(
            StockSummaryEntry(
                stock_ticker=ticker,
                stock_name=next(
                    (item.stock_name for item in matched if item.stock_name is not None),
                    None,
                ),
                sector=next(
                    (item.sector for item in matched if item.sector is not None),
                    None,
                ),
                holder_count=len(rows),
                shares_held=sum(row.shares_held for row in rows),
                market_value_usd=sum(
                    (row.market_value_usd or Decimal(0) for row in rows), Decimal(0)
                ),
                shares_change_qoq=sum(row.shares_change_qoq or 0 for row in rows),
                enriched_positions=len(matched),
            )
        )
    stocks.sort(key=lambda row: row.market_value_usd, reverse=True)

    changed = [row for row in current if row.shares_change_qoq is not None]
    buys = sorted(
        (row for row in changed if (row.shares_change_qoq or 0) > 0),
        key=lambda row: row.shares_change_qoq or 0,
        reverse=True,
    )
    sells = sorted(
        (row for row in changed if (row.shares_change_qoq or 0) < 0),
        key=lambda row: row.shares_change_qoq or 0,
    )
    observed = [row.observed_at for row in matching_snapshots.values()]
    observed.extend(row.observed_at for row in matching_enrichments.values())

    return InstitutionalOverviewResponse(
        quarter_end=quarter_end,
        total_funds=len(fund_rows),
        total_stocks=len(stock_rows),
        total_positions=len(current),
        funds=funds[:fund_limit],
        enrichment_only_funds=enrichment_only[:fund_limit],
        stocks=stocks[:stock_limit],
        top_buys=[_move(row) for row in buys[:mover_limit]],
        top_sells=[_move(row) for row in sells[:mover_limit]],
        enrichment_coverage=EnrichmentCoverage(
            matched_funds=sum(1 for cik in matching_snapshots if cik in fund_rows),
            enrichment_only_funds=len(enrichment_only),
            matched_positions=sum(1 for key in matching_enrichments if key in official_positions),
            observed_at=max(observed, default=None),
        ),
        coverage_note=_COVERAGE_NOTE,
    )
