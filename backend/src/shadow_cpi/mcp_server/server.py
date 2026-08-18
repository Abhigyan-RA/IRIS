"""The MCP server: the same data, exposed to AI agents and IDEs.

The dashboard is one way in; this is the other. An agent connected to this server
can ask about prices, what a commodity feeds into, and who holds a stock, without
anybody writing a scraper or an API client first.

Two conventions make the tools pleasant for an agent to use:

- Every tool returns a structured result with a ``found`` flag and a ``message``,
  rather than raising. An agent handles "not found, here is why" far better than an
  exception, and a missing data store is reported the same way instead of appearing
  as an empty answer.
- Numbers are returned as plain numbers rather than strings, because that is what
  a model will try to compute with.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from shadow_cpi.ai.gemini import GeminiError
from shadow_cpi.api.dependencies import ApiDependencies
from shadow_cpi.api.freshness import is_stale
from shadow_cpi.db.neo4j.repository import MAX_RIPPLE_DEPTH

SERVER_NAME = "shadow-cpi"

TOOL_NAMES: tuple[str, ...] = (
    "get_commodity_price_trend",
    "analyze_supply_chain_impact",
    "get_institutional_holders",
    "check_data_freshness",
    "ask_shadow_cpi_copilot",
)

# History window used when reporting a trend, matching the dashboard's default.
_TREND_DAYS = 30

_PERCENT_PRECISION = Decimal("0.001")


class PriceTrend(BaseModel):
    """Latest price and recent trend for one commodity.

    Attributes:
        found: Whether the commodity is tracked and has a recorded price.
        message: Explanation when it is not, otherwise a short summary.
        commodity: The commodity asked about.
        price: Most recent price.
        currency: Currency of the price.
        unit: What one unit refers to.
        trend_pct: Change across the reported window, in percent.
        recorded_at: When the price was observed.
        source_name: Where it came from.
        source_url: Exact page or endpoint it came from.
    """

    found: bool
    message: str
    commodity: str
    price: float | None = None
    currency: str | None = None
    unit: str | None = None
    trend_pct: float | None = None
    recorded_at: str | None = None
    source_name: str | None = None
    source_url: str | None = None


class SupplyChainImpact(BaseModel):
    """What a commodity feeds into.

    Attributes:
        found: Whether anything downstream is mapped for it.
        message: Short summary of what was found.
        commodity: The commodity asked about.
        industries: Industries reached.
        components: Intermediate goods reached.
        links: Each step, as "source -> relationship -> target".
    """

    found: bool
    message: str
    commodity: str
    industries: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class Holder(BaseModel):
    """One fund's position in a stock.

    Attributes:
        filer: Name of the fund.
        cik: The fund's identifier.
        shares_held: Shares held at quarter end.
        delta_pct: Change versus the previous quarter, in percent, when known.
        quarter_end: Quarter the disclosure covers.
        source_url: Filing the numbers came from.
    """

    filer: str
    cik: str
    shares_held: int
    delta_pct: float | None
    quarter_end: str
    source_url: str | None


class Holders(BaseModel):
    """Every fund reporting a position in one stock.

    Attributes:
        found: Whether any fund reported it.
        message: Short summary of what was found.
        ticker: The stock asked about.
        holders: The positions, largest first.
    """

    found: bool
    message: str
    ticker: str
    holders: list[Holder] = Field(default_factory=list)


class Freshness(BaseModel):
    """How current the data for one commodity is.

    Attributes:
        found: Whether the commodity has a recorded price.
        message: Short summary.
        commodity: The commodity asked about.
        recorded_at: When the newest price was observed.
        age_hours: How old that price is, in hours.
        is_stale: Whether it is older than its category's freshness target.
        source_name: Where it came from.
    """

    found: bool
    message: str
    commodity: str
    recorded_at: str | None = None
    age_hours: float | None = None
    is_stale: bool | None = None
    source_name: str | None = None


class CopilotReply(BaseModel):
    """An answer grounded in stored data.

    Attributes:
        found: Whether an answer could be grounded in stored data.
        answer: The reply, in plain language.
        sources: URLs of the data behind it, so the agent can cite them onward.
        data_as_of: Timestamp of the newest evidence used, when prices were involved.
    """

    found: bool
    answer: str
    sources: list[str] = Field(default_factory=list)
    data_as_of: str | None = None


def _percent(current: Decimal, previous: Decimal) -> float | None:
    """Return the percentage change between two prices.

    Args:
        current: The newer price.
        previous: The older price.

    Returns:
        The change in percent, or None when a percentage would be meaningless.
    """
    if previous == 0:
        return None
    change = (current - previous) / previous * Decimal(100)
    return float(change.quantize(_PERCENT_PRECISION, rounding=ROUND_HALF_UP))


def build_server(dependencies: ApiDependencies) -> FastMCP:
    """Build the MCP server with its tools bound to the given data stores.

    Args:
        dependencies: Data stores the tools read from. Passed in, so tests exercise
            the tools against fakes and the production wiring lives in one place.

    Returns:
        A server ready to be connected to a transport.
    """
    server = FastMCP(SERVER_NAME)

    @server.tool(
        name="get_commodity_price_trend",
        description=(
            "Latest public spot price and recent trend for a commodity, freight "
            "lane, or index, with the source it came from."
        ),
    )
    async def get_commodity_price_trend(commodity: str) -> PriceTrend:
        """Report the latest price and trend for one commodity.

        Args:
            commodity: What to look up, for example ``Copper`` or ``FBX_Global``.

        Returns:
            The latest price with its trend, or an explanation of why not.
        """
        prices = dependencies.prices
        if prices is None:
            return PriceTrend(
                found=False,
                message="Price data is not available: no price store is configured",
                commodity=commodity,
            )

        latest = await prices.latest_price(commodity)
        if latest is None:
            return PriceTrend(
                found=False,
                message=f"No price has been recorded for {commodity!r}",
                commodity=commodity,
            )

        history = await prices.price_history(commodity, _TREND_DAYS)
        trend = _percent(history[-1].price, history[0].price) if len(history) > 1 else None
        return PriceTrend(
            found=True,
            message=f"Latest price for {commodity} with a {_TREND_DAYS}-day trend",
            commodity=commodity,
            price=float(latest.price),
            currency=latest.currency,
            unit=latest.unit,
            trend_pct=trend,
            recorded_at=latest.recorded_at.isoformat(),
            source_name=latest.source_name,
            source_url=latest.source_url,
        )

    @server.tool(
        name="analyze_supply_chain_impact",
        description=(
            "Downstream components and industries affected by a commodity price "
            "move, traversing the supply-chain graph."
        ),
    )
    async def analyze_supply_chain_impact(
        commodity: str,
        max_depth: int = 2,
    ) -> SupplyChainImpact:
        """Report what a commodity feeds into.

        Args:
            commodity: Commodity to start from.
            max_depth: How many steps downstream to follow. Values above the
                supported maximum are clamped rather than refused, since an agent
                asking for "everything" should still get a useful answer.

        Returns:
            The components and industries reached.
        """
        graph = dependencies.graph
        if graph is None:
            return SupplyChainImpact(
                found=False,
                message="Supply-chain data is not available: no graph store is configured",
                commodity=commodity,
            )

        depth = max(1, min(max_depth, MAX_RIPPLE_DEPTH))
        links = await graph.ripple_effect(commodity, depth)
        industries = sorted({link.target for link in links if link.target_label == "Industry"})
        components = sorted({link.target for link in links if link.target_label == "Component"})

        return SupplyChainImpact(
            found=bool(links),
            message=(
                f"{len(industries)} industries and {len(components)} components "
                f"depend on {commodity}"
                if links
                else f"Nothing downstream of {commodity!r} is mapped yet"
            ),
            commodity=commodity,
            industries=industries,
            components=components,
            links=[f"{link.source} -> {link.relationship} -> {link.target}" for link in links],
        )

    @server.tool(
        name="get_institutional_holders",
        description=(
            "Investment managers reporting a position in a stock, with the change "
            "since the previous quarter, from public quarterly filings."
        ),
    )
    async def get_institutional_holders(ticker: str) -> Holders:
        """Report the funds holding one stock.

        Args:
            ticker: Ticker symbol to look up.

        Returns:
            The reported positions, largest first.
        """
        holdings = dependencies.holdings
        if holdings is None:
            return Holders(
                found=False,
                message="Holdings data is not available: no holdings store is configured",
                ticker=ticker.upper(),
            )

        rows = await holdings.holders_of(ticker)
        ordered = sorted(rows, key=lambda row: row.market_value_usd or Decimal(0), reverse=True)
        holders: list[Holder] = []
        for row in ordered:
            change = row.shares_change_qoq
            previous = None if change is None else row.shares_held - change
            delta = (
                _percent(Decimal(row.shares_held), Decimal(previous))
                if previous is not None and previous > 0
                else None
            )
            holders.append(
                Holder(
                    filer=row.filer_name,
                    cik=row.filer_cik,
                    shares_held=row.shares_held,
                    delta_pct=delta,
                    quarter_end=row.quarter_end.isoformat(),
                    source_url=row.source_url,
                )
            )

        return Holders(
            found=bool(holders),
            message=(
                f"{len(holders)} managers reported a position in {ticker.upper()}"
                if holders
                else f"No filings recorded for {ticker.upper()}"
            ),
            ticker=ticker.upper(),
            holders=holders,
        )

    @server.tool(
        name="check_data_freshness",
        description=(
            "How current the stored data for a commodity is, so an answer can say "
            "how recent its evidence was."
        ),
    )
    async def check_data_freshness(commodity: str) -> Freshness:
        """Report how old the newest price for one commodity is.

        Args:
            commodity: What to check.

        Returns:
            The age of the newest price and whether it counts as stale.
        """
        prices = dependencies.prices
        if prices is None:
            return Freshness(
                found=False,
                message="Price data is not available: no price store is configured",
                commodity=commodity,
            )

        latest = await prices.latest_price(commodity)
        if latest is None:
            return Freshness(
                found=False,
                message=f"No price has been recorded for {commodity!r}",
                commodity=commodity,
            )

        now = datetime.now(UTC)
        age_hours = (now - latest.recorded_at).total_seconds() / 3600
        stale = is_stale(latest.sector, latest.recorded_at, now)
        return Freshness(
            found=True,
            message=(
                f"{commodity} was last updated {age_hours:.1f} hours ago"
                + (" and is behind its freshness target" if stale else "")
            ),
            commodity=commodity,
            recorded_at=latest.recorded_at.isoformat(),
            age_hours=round(age_hours, 2),
            is_stale=stale,
            source_name=latest.source_name,
        )

    @server.tool(
        name="ask_shadow_cpi_copilot",
        description=(
            "Ask a free-form question about commodity prices, supply chains, or "
            "fund holdings. The answer is grounded in stored data and cites it."
        ),
    )
    async def ask_shadow_cpi_copilot(question: str) -> CopilotReply:
        """Answer a free-form question from stored data.

        Args:
            question: The question, in plain language.

        Returns:
            The answer with its sources, or an explanation of why none was produced.
            Failures are reported in the payload rather than raised, so a connected
            agent can relay the reason instead of surfacing a stack trace.
        """
        copilot = dependencies.copilot
        if copilot is None:
            return CopilotReply(
                found=False,
                answer="The copilot is not available: no model client is configured",
            )

        try:
            reply = await copilot.ask(question)
        except (GeminiError, ValueError) as error:
            return CopilotReply(found=False, answer=f"Could not answer: {error}")

        return CopilotReply(
            found=bool(reply.sources),
            answer=reply.answer,
            sources=reply.sources,
            data_as_of=reply.data_as_of.isoformat() if reply.data_as_of else None,
        )

    return server
