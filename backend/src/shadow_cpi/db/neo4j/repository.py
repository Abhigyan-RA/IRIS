"""The supply-chain graph: what a commodity feeds into, and who is exposed to it.

Prices answer "what changed". This graph answers "so what": copper is refined
into stator coils, which are required for electric-vehicle manufacturing, and
these funds hold companies exposed to it. Storing that as a graph rather than
extra SQL tables is a deliberate choice, because the interesting questions are
about paths of unknown length ("everything downstream of copper"), which graph
traversal expresses directly.

Two things in Cypher cannot be bound as parameters: node labels and relationship
types, and the length of a variable-length path. Anything that would otherwise be
interpolated into a query is therefore checked against a fixed allow-list first,
and rejected if it is not on it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

# Node labels this project uses, mapped to the property that identifies them.
ALLOWED_LABELS: Mapping[str, str] = {
    "Commodity": "name",
    "Component": "name",
    "Industry": "name",
    "Company": "ticker",
    "Filer": "cik",
}

# Relationship types this project uses.
#
# REFINED_INTO / REQUIRED_FOR describe the physical supply chain.
# IMPACTS_COST_OF carries a weight: how much of an industry's cost this input is.
# HOLDS is a fund's position in a company.
# EXPOSED_TO links a company back to the commodities that move its costs, which
# is what lets one click answer both "what does this hit" and "who is positioned
# for it".
ALLOWED_RELATIONSHIPS: frozenset[str] = frozenset(
    {
        "REFINED_INTO",
        "REQUIRED_FOR",
        "IMPACTS_COST_OF",
        "HOLDS",
        "EXPOSED_TO",
    }
)

# Traversals are capped: an unbounded path length on a well-connected graph can
# take a very long time and return more than any screen can show.
MAX_RIPPLE_DEPTH = 5


class GraphSession(Protocol):
    """Runs Cypher against the graph.

    Narrow on purpose, so tests can supply a fake with a single method.
    """

    async def run(
        self,
        query: str,
        params: Mapping[str, object] | None = None,
    ) -> list[Mapping[str, object]]:
        """Run a query and return its rows."""
        ...


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A node to create or match.

    Attributes:
        label: Node label, which must be one of the known labels.
        key: Identifying property name, such as ``name`` or ``ticker``.
        value: Value of the identifying property.
        properties: Extra properties to set on the node.
    """

    label: str
    key: str
    value: str
    properties: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject labels that are not on the allow-list.

        Raises:
            ValueError: If the label is unknown.
        """
        if self.label not in ALLOWED_LABELS:
            raise ValueError(f"Unknown node label {self.label!r}; add it to ALLOWED_LABELS first")


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """A relationship to create between two nodes.

    Attributes:
        source: Node the relationship starts at.
        relationship: Relationship type, which must be one of the known types.
        target: Node the relationship points to.
        properties: Extra properties to set on the relationship, such as a weight.
    """

    source: GraphNode
    relationship: str
    target: GraphNode
    properties: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject relationship types that are not on the allow-list.

        Raises:
            ValueError: If the relationship type is unknown.
        """
        if self.relationship not in ALLOWED_RELATIONSHIPS:
            raise ValueError(
                f"Unknown relationship {self.relationship!r}; "
                "add it to ALLOWED_RELATIONSHIPS first"
            )


@dataclass(frozen=True, slots=True)
class RippleLink:
    """One step in a downstream chain.

    Attributes:
        source: Name of the upstream node.
        relationship: How it connects.
        target: Name of the downstream node.
        target_label: What kind of thing the downstream node is.
        weight: Share of the target's cost attributable to the source, when known.
    """

    source: str
    relationship: str
    target: str
    target_label: str
    weight: float | None = None


@dataclass(frozen=True, slots=True)
class HoldingLink:
    """A fund's position in a company, as written to the graph.

    Attributes:
        filer_cik: Fund identifier. Normalized to ten digits when written.
        filer_name: Fund name.
        ticker: Company ticker symbol.
        company_name: Company name.
        shares: Shares held at the end of the quarter.
        quarter: Quarter label, such as ``2026-Q2``.
        delta_pct: Change versus the previous quarter, in percent, when known.
    """

    filer_cik: str
    filer_name: str
    ticker: str
    company_name: str
    shares: int
    quarter: str
    delta_pct: float | None = None


class Neo4jSupplyChainRepository:
    """Reads and writes the supply-chain and holdings graph."""

    def __init__(self, session: GraphSession) -> None:
        """Create the repository.

        Args:
            session: Graph session, passed in so tests can substitute a fake.
        """
        self._session = session

    async def apply_constraints(self) -> None:
        """Create one uniqueness constraint per node type.

        These constraints are what make ``MERGE`` safe: without them, two
        collectors writing "Copper" at the same time can create two Copper nodes,
        and the graph quietly splits in half.
        """
        for label, key in ALLOWED_LABELS.items():
            await self._session.run(
                f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            )

    async def merge_node(self, node: GraphNode) -> None:
        """Create a node if it does not exist, or update its properties if it does.

        Args:
            node: The node to write.
        """
        await self._session.run(
            f"MERGE (n:{node.label} {{{node.key}: $value}}) SET n += $properties",
            {"value": node.value, "properties": dict(node.properties)},
        )

    async def merge_edge(self, edge: GraphEdge) -> None:
        """Create a relationship if it does not exist, or update its properties.

        Args:
            edge: The relationship to write.
        """
        await self._session.run(
            f"MERGE (source:{edge.source.label} {{{edge.source.key}: $source_value}}) "
            f"MERGE (target:{edge.target.label} {{{edge.target.key}: $target_value}}) "
            f"MERGE (source)-[rel:{edge.relationship}]->(target) "
            "SET rel += $properties",
            {
                "source_value": edge.source.value,
                "target_value": edge.target.value,
                "properties": dict(edge.properties),
            },
        )

    async def seed(
        self,
        nodes: Sequence[GraphNode] | None = None,
        edges: Sequence[GraphEdge] | None = None,
    ) -> dict[str, int]:
        """Load the starting graph.

        Everything is merged rather than created, so running this against a graph
        that already holds data updates it instead of duplicating it.

        Args:
            nodes: Nodes to write. Defaults to the shipped seed data.
            edges: Relationships to write. Defaults to the shipped seed data.

        Returns:
            How many nodes and relationships were written.
        """
        from shadow_cpi.db.neo4j.seed import SEED_EDGES, SEED_NODES

        resolved_nodes = list(nodes if nodes is not None else SEED_NODES)
        resolved_edges = list(edges if edges is not None else SEED_EDGES)

        for node in resolved_nodes:
            await self.merge_node(node)
        for edge in resolved_edges:
            await self.merge_edge(edge)

        return {"nodes": len(resolved_nodes), "edges": len(resolved_edges)}

    async def ripple_effect(self, commodity: str, max_depth: int = 2) -> list[RippleLink]:
        """Return what a commodity feeds into, following the chain downstream.

        Args:
            commodity: Commodity to start from, for example ``Copper``.
            max_depth: How many steps downstream to follow, from 1 to
                ``MAX_RIPPLE_DEPTH``.

        Returns:
            One entry per relationship found, in traversal order. Empty when the
            commodity is unknown or has no downstream links.

        Raises:
            ValueError: If the depth is outside the allowed range. The depth is
                checked rather than bound as a parameter because Cypher does not
                allow a path length to be parameterized.
        """
        if max_depth < 1 or max_depth > MAX_RIPPLE_DEPTH:
            raise ValueError(f"max_depth must be between 1 and {MAX_RIPPLE_DEPTH}")

        rows = await self._session.run(
            "MATCH path = (start:Commodity {name: $name})"
            f"-[:REFINED_INTO|REQUIRED_FOR|IMPACTS_COST_OF*1..{max_depth}]->(downstream) "
            "UNWIND relationships(path) AS rel "
            "WITH DISTINCT rel, startNode(rel) AS source, endNode(rel) AS target "
            "RETURN coalesce(source.name, source.ticker) AS source, "
            "type(rel) AS relationship, "
            "coalesce(target.name, target.ticker) AS target, "
            "head(labels(target)) AS target_label, "
            "rel.weight AS weight",
            {"name": commodity},
        )
        return [
            RippleLink(
                source=str(row["source"]),
                relationship=str(row["relationship"]),
                target=str(row["target"]),
                target_label=str(row["target_label"]),
                weight=float(str(row["weight"])) if row.get("weight") is not None else None,
            )
            for row in rows
        ]

    async def filers_exposed_to(self, commodity: str) -> list[Mapping[str, object]]:
        """Return the funds holding companies exposed to a commodity.

        Args:
            commodity: Commodity to look up.

        Returns:
            One row per fund and company pair, with the fund's position details.
        """
        return await self._session.run(
            "MATCH (filer:Filer)-[held:HOLDS]->(company:Company)"
            "-[:EXPOSED_TO]->(commodity:Commodity {name: $name}) "
            "RETURN filer.name AS filer, filer.cik AS cik, company.ticker AS ticker, "
            "held.shares AS shares, held.quarter AS quarter, held.delta_pct AS delta_pct "
            "ORDER BY held.shares DESC",
            {"name": commodity},
        )

    async def link_holding(self, holding: HoldingLink) -> None:
        """Record that a fund holds a position in a company.

        Args:
            holding: The position to write. Grouped into one value object because
                these fields only make sense together.
        """
        from shadow_cpi.shared import normalize_cik

        await self._session.run(
            "MERGE (filer:Filer {cik: $cik}) SET filer.name = $filer_name "
            "MERGE (company:Company {ticker: $ticker}) SET company.name = $company_name "
            "MERGE (filer)-[held:HOLDS {quarter: $quarter}]->(company) "
            "SET held.shares = $shares, held.delta_pct = $delta_pct",
            {
                "cik": normalize_cik(holding.filer_cik),
                "filer_name": holding.filer_name,
                "ticker": holding.ticker.strip().upper(),
                "company_name": holding.company_name,
                "shares": holding.shares,
                "quarter": holding.quarter,
                "delta_pct": holding.delta_pct,
            },
        )

    async def link_exposure(self, ticker: str, commodity: str) -> None:
        """Record that a company's costs are exposed to a commodity.

        Args:
            ticker: Company ticker symbol. Case is normalized.
            commodity: Commodity the company is exposed to.
        """
        await self._session.run(
            "MERGE (company:Company {ticker: $ticker}) "
            "MERGE (commodity:Commodity {name: $name}) "
            "MERGE (company)-[:EXPOSED_TO]->(commodity)",
            {"ticker": ticker.strip().upper(), "name": commodity},
        )
