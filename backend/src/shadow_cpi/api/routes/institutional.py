"""Institutional holdings endpoints.

These answer "what did the professional money do this quarter", which is a second,
independent signal alongside the raw prices: a commodity moving is one thing, funds
positioning for it is another.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from shadow_cpi.api.dependencies import require_holdings
from shadow_cpi.db.protocols import HoldingsReader
from shadow_cpi.shared import InstitutionalHolding, normalize_cik

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
    """

    stock_ticker: str
    shares_held: int
    market_value_usd: Decimal | None
    pct_portfolio: Decimal | None
    shares_change_qoq: int | None
    delta_pct: Decimal | None
    quarter_end: date
    source_url: str | None


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
    filer_cik: Annotated[str, Path(min_length=1, max_length=20)],
    quarter_end: Annotated[date | None, Query()] = None,
) -> FilerHoldingsResponse:
    """Return one fund's reported positions.

    Args:
        holdings: Holdings store to read from.
        filer_cik: The fund's identifier, in any of the forms it is written in.
        quarter_end: Restrict to one quarter, or omit for every quarter held.

    Returns:
        The positions, largest first.

    Raises:
        HTTPException: If the identifier is not a valid fund identifier. Rejecting
            it here means the request never reaches the database.
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
            )
            for row in ordered
        ],
    )
