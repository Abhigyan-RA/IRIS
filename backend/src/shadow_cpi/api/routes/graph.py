"""Supply-chain graph endpoint.

A price move on its own means little. This endpoint answers what a commodity feeds
into, and which funds hold companies exposed to it, so that a number becomes a
consequence.

The plain-language explanation of why a move matters is generated separately and is
absent until that is configured, which is why the field is optional rather than
invented here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from shadow_cpi.api.dependencies import (
    ApiDependencies,
    SupplyChainReader,
    get_dependencies,
    require_graph,
)
from shadow_cpi.db.neo4j.repository import MAX_RIPPLE_DEPTH, RippleLink

# Two steps is the useful default: far enough to reach an industry, close enough
# that the result still fits on a screen.
_DEFAULT_DEPTH = 2

router = APIRouter(prefix="/api/graph", tags=["graph"])


class GraphNodeOut(BaseModel):
    """One thing in the chain.

    Attributes:
        name: Its name.
        kind: What it is, such as ``Commodity``, ``Component``, or ``Industry``.
    """

    name: str
    kind: str


class GraphLinkOut(BaseModel):
    """One step in the chain.

    Attributes:
        source: Where the step starts.
        relationship: How the two are connected.
        target: Where the step leads.
        weight: Share of the target's cost attributable to the source, when known.
    """

    source: str
    relationship: str
    target: str
    weight: float | None


class RippleResponse(BaseModel):
    """What a commodity affects downstream.

    Attributes:
        commodity: The commodity asked about.
        depth: How many steps downstream were followed.
        nodes: Everything reached, for drawing the graph.
        links: The steps between them.
        affected_industries: Industries reached, which is the short answer to
            "who does this hit".
        exposed_filers: Funds holding companies exposed to the commodity.
        explanation: Plain-language summary of why the move matters. Absent until
            explanation generation is configured.
    """

    commodity: str
    depth: int
    nodes: list[GraphNodeOut]
    links: list[GraphLinkOut]
    affected_industries: list[str]
    exposed_filers: list[dict[str, object]]
    explanation: str | None = None


def _collect_nodes(commodity: str, links: list[RippleLink]) -> list[GraphNodeOut]:
    """Build the node list implied by a set of steps.

    Args:
        commodity: The commodity the traversal started from.
        links: The steps found.

    Returns:
        Every distinct thing reached, starting with the commodity itself, in the
        order it was encountered.
    """
    nodes: dict[str, GraphNodeOut] = {commodity: GraphNodeOut(name=commodity, kind="Commodity")}
    for link in links:
        nodes.setdefault(link.source, GraphNodeOut(name=link.source, kind="Commodity"))
        nodes[link.target] = GraphNodeOut(name=link.target, kind=link.target_label)
    return list(nodes.values())


@router.get(
    "/ripple/{commodity}",
    response_model=RippleResponse,
    summary="What a commodity affects downstream",
)
async def read_ripple(
    graph: Annotated[SupplyChainReader, Depends(require_graph)],
    dependencies: Annotated[ApiDependencies, Depends(get_dependencies)],
    commodity: Annotated[str, Path(min_length=1, max_length=255)],
    depth: Annotated[int, Query(ge=1, le=MAX_RIPPLE_DEPTH)] = _DEFAULT_DEPTH,
) -> RippleResponse:
    """Return the chain downstream of a commodity.

    Args:
        graph: Graph store to read from.
        dependencies: Container holding the optional explanation writer.
        commodity: Commodity to start from.
        depth: How many steps downstream to follow.

    Returns:
        The nodes and steps found, the industries affected, and the funds exposed.
        A commodity with nothing downstream returns an empty graph rather than an
        error: not yet mapped is a valid answer. The explanation appears only when
        an explanation writer is configured and there is something to explain.
    """
    links = await graph.ripple_effect(commodity, depth)
    exposure = await graph.filers_exposed_to(commodity)

    industries = sorted({link.target for link in links if link.target_label == "Industry"})

    explanation: str | None = None
    explainer = dependencies.explainer
    if explainer is not None and links:
        explanation = await explainer.explain(
            commodity=commodity,
            price_summary=await _summarise_price(dependencies, commodity),
            links=links,
        )

    return RippleResponse(
        commodity=commodity,
        depth=depth,
        nodes=_collect_nodes(commodity, links),
        links=[
            GraphLinkOut(
                source=link.source,
                relationship=link.relationship,
                target=link.target,
                weight=link.weight,
            )
            for link in links
        ],
        affected_industries=industries,
        exposed_filers=[dict(row) for row in exposure],
        explanation=explanation,
    )


async def _summarise_price(dependencies: ApiDependencies, commodity: str) -> str:
    """Describe a commodity's latest move in one phrase.

    The explanation is grounded in real numbers where they exist, so this phrase is
    built from the stored price rather than left to the model to imagine.

    Args:
        dependencies: Container holding the optional price store.
        commodity: Commodity to describe.

    Returns:
        A short description of the latest move, or a note that no price is on record.
    """
    prices = dependencies.prices
    if prices is None:
        return "no recent price on record"

    latest = await prices.latest_price(commodity)
    if latest is None:
        return "no recent price on record"
    if latest.pct_change_1d is None:
        return f"{latest.price} {latest.currency} per {latest.unit}"
    direction = "up" if latest.pct_change_1d >= 0 else "down"
    return (
        f"{direction} {abs(latest.pct_change_1d)} percent, at "
        f"{latest.price} {latest.currency} per {latest.unit}"
    )
