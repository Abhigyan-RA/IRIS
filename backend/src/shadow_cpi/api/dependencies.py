"""What the API needs in order to answer a request.

Routes never construct a database connection or an HTTP client. They receive the
things they need through this container, which is what makes every endpoint
testable against fakes and keeps the wiring in one readable place.

Each field is optional. An endpoint whose dependency is absent replies that the
feature is unavailable, rather than failing at startup, so a partially configured
deployment still serves everything it can.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hmac import compare_digest
from typing import TYPE_CHECKING, Protocol

from fastapi import Header, HTTPException, Request, status

from shadow_cpi.config import Settings

if TYPE_CHECKING:
    from shadow_cpi.ai.copilot import CopilotAnswer
    from shadow_cpi.db.neo4j.repository import RippleLink
    from shadow_cpi.db.protocols import HealthEventReader, HoldingsReader, PriceReader
    from shadow_cpi.ingestion.brightdata.self_heal import RunOutcome


class SupplyChainReader(Protocol):
    """Reads the supply-chain graph.

    Declared here as the narrow view the API needs, so routes do not depend on the
    full graph repository, which can also write.
    """

    async def ripple_effect(self, commodity: str, max_depth: int = 2) -> list[RippleLink]:
        """Return what a commodity feeds into, downstream."""
        ...

    async def filers_exposed_to(self, commodity: str) -> list[Mapping[str, object]]:
        """Return the funds holding companies exposed to a commodity."""
        ...


class CollectorHealer(Protocol):
    """Reads a page and repairs the attempt if the page has changed."""

    async def run(self, collector_id: str, source_name: str, url: str) -> RunOutcome:
        """Run the collector, healing it if the site changed, and report what happened."""
        ...


class Copilot(Protocol):
    """Answers a free-form question from stored data."""

    async def ask(self, question: str) -> CopilotAnswer:
        """Return an answer with the sources it used."""
        ...


class RippleExplainer(Protocol):
    """Explains in plain language why a commodity move matters."""

    async def explain(
        self,
        commodity: str,
        price_summary: str,
        links: Sequence[RippleLink],
    ) -> str | None:
        """Return the explanation, or None when there is nothing to ground it in."""
        ...


@dataclass(frozen=True, slots=True)
class ApiDependencies:
    """Everything the routes may need.

    Attributes:
        prices: Reads price history.
        holdings: Reads quarterly fund disclosures.
        health_events: Reads the collector audit trail.
        graph: Reads supply-chain relationships.
        healer: Runs a collector on demand and repairs it if needed.
        copilot: Answers free-form questions from stored data.
        explainer: Writes the plain-language explanation for a ripple result.
    """

    prices: PriceReader | None = None
    holdings: HoldingsReader | None = None
    health_events: HealthEventReader | None = None
    graph: SupplyChainReader | None = None
    healer: CollectorHealer | None = None
    copilot: Copilot | None = None
    explainer: RippleExplainer | None = None


def get_settings_from_request(request: Request) -> Settings:
    """Return the settings the running application was built with.

    Args:
        request: The incoming request.

    Returns:
        The active settings.
    """
    settings: Settings = request.app.state.settings
    return settings


def get_dependencies(request: Request) -> ApiDependencies:
    """Return the container attached to the running application.

    Args:
        request: The incoming request.

    Returns:
        The dependency container.
    """
    dependencies: ApiDependencies = request.app.state.dependencies
    return dependencies


def require_prices(request: Request) -> PriceReader:
    """Return the price reader, or report that prices are unavailable.

    Args:
        request: The incoming request.

    Returns:
        The configured price reader.

    Raises:
        HTTPException: If no price store is configured.
    """
    prices = get_dependencies(request).prices
    if prices is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Price data is not available because no price store is configured",
        )
    return prices


def require_holdings(request: Request) -> HoldingsReader:
    """Return the holdings reader, or report that holdings are unavailable.

    Args:
        request: The incoming request.

    Returns:
        The configured holdings reader.

    Raises:
        HTTPException: If no holdings store is configured.
    """
    holdings = get_dependencies(request).holdings
    if holdings is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Holdings data is not available because no holdings store is configured",
        )
    return holdings


def require_health_events(request: Request) -> HealthEventReader:
    """Return the health event reader, or report that the feed is unavailable.

    Args:
        request: The incoming request.

    Returns:
        The configured health event reader.

    Raises:
        HTTPException: If no event store is configured.
    """
    events = get_dependencies(request).health_events
    if events is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The pipeline health feed is not available because no event store is configured",
        )
    return events


def require_graph(request: Request) -> SupplyChainReader:
    """Return the graph reader, or report that the graph is unavailable.

    Args:
        request: The incoming request.

    Returns:
        The configured graph reader.

    Raises:
        HTTPException: If no graph store is configured.
    """
    graph = get_dependencies(request).graph
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supply-chain graph data is not available because no graph store is configured",
        )
    return graph


def require_healer(request: Request) -> CollectorHealer:
    """Return the repair runner, or report that repairs are unavailable.

    Args:
        request: The incoming request.

    Returns:
        The configured repair runner.

    Raises:
        HTTPException: If no runner is configured.
    """
    healer = get_dependencies(request).healer
    if healer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collector repair is not available because no scraping runner is configured",
        )
    return healer


def require_copilot(request: Request) -> Copilot:
    """Return the copilot, or report that it is unavailable.

    Args:
        request: The incoming request.

    Returns:
        The configured copilot.

    Raises:
        HTTPException: If no copilot is configured, which is the case when no model
            key is available.
    """
    copilot = get_dependencies(request).copilot
    if copilot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The copilot is not available because no model client is configured",
        )
    return copilot


def require_cron_secret(request: Request, x_cron_secret: str | None = Header(default=None)) -> None:
    """Reject a request that does not carry the shared secret.

    Guards the endpoints that spend money or act on a live website. The comparison
    is constant-time so that a wrong value cannot be narrowed down by timing, and
    the expected value is never echoed back.

    Args:
        request: The incoming request.
        x_cron_secret: Secret supplied by the caller.

    Raises:
        HTTPException: If the secret is missing or wrong.
    """
    settings: Settings = request.app.state.settings
    expected = settings.cron_secret.get_secret_value()
    if x_cron_secret is None or not compare_digest(x_cron_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-Cron-Secret header is required for this endpoint",
        )
