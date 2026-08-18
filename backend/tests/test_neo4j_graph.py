"""Tests for the supply-chain graph: constraints, seeding, and traversals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from shadow_cpi.db.neo4j.repository import (
    ALLOWED_LABELS,
    ALLOWED_RELATIONSHIPS,
    MAX_RIPPLE_DEPTH,
    GraphEdge,
    GraphNode,
    HoldingLink,
    Neo4jSupplyChainRepository,
)
from shadow_cpi.db.neo4j.seed import SEED_EDGES, SEED_NODES


class FakeSession:
    """Records Cypher instead of running it, so tests need no graph database."""

    def __init__(self, rows: Sequence[Mapping[str, object]] = ()) -> None:
        self.queries: list[tuple[str, Mapping[str, object]]] = []
        self._rows = list(rows)

    async def run(
        self, query: str, params: Mapping[str, object] | None = None
    ) -> list[Mapping[str, object]]:
        self.queries.append((query, dict(params or {})))
        return self._rows


def _cypher_of(session: FakeSession) -> str:
    return "\n".join(query for query, _ in session.queries)


class TestConstraints:
    @pytest.mark.asyncio
    async def test_creates_one_uniqueness_constraint_per_node_type(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).apply_constraints()

        cypher = _cypher_of(session)
        assert "FOR (n:Commodity) REQUIRE n.name IS UNIQUE" in cypher
        assert "FOR (n:Industry) REQUIRE n.name IS UNIQUE" in cypher
        assert "FOR (n:Component) REQUIRE n.name IS UNIQUE" in cypher
        assert "FOR (n:Company) REQUIRE n.ticker IS UNIQUE" in cypher
        assert "FOR (n:Filer) REQUIRE n.cik IS UNIQUE" in cypher

    @pytest.mark.asyncio
    async def test_constraints_can_be_applied_repeatedly(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).apply_constraints()

        assert _cypher_of(session).count("IF NOT EXISTS") == len(ALLOWED_LABELS)


class TestSeeding:
    @pytest.mark.asyncio
    async def test_seed_writes_every_node_and_edge(self) -> None:
        session = FakeSession()

        summary = await Neo4jSupplyChainRepository(session).seed()

        assert summary == {"nodes": len(SEED_NODES), "edges": len(SEED_EDGES)}
        assert len(session.queries) == len(SEED_NODES) + len(SEED_EDGES)

    @pytest.mark.asyncio
    async def test_seed_uses_merge_so_it_can_be_rerun(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).seed()

        assert "CREATE (" not in _cypher_of(session)
        assert _cypher_of(session).count("MERGE") >= len(SEED_NODES)

    @pytest.mark.asyncio
    async def test_seed_passes_values_as_parameters(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).seed()

        assert all("Copper" not in query for query, _ in session.queries)
        assert any("Copper" in params.values() for _, params in session.queries)

    def test_seed_connects_a_commodity_to_a_downstream_industry(self) -> None:
        relationships = {edge.relationship for edge in SEED_EDGES}

        assert "REFINED_INTO" in relationships
        assert "REQUIRED_FOR" in relationships
        assert "IMPACTS_COST_OF" in relationships

    def test_seed_bridges_holdings_to_commodities(self) -> None:
        """The EXPOSED_TO edge is what makes holdings and prices one story."""
        relationships = {edge.relationship for edge in SEED_EDGES}

        assert "HOLDS" in relationships
        assert "EXPOSED_TO" in relationships

    def test_seed_uses_only_known_labels_and_relationships(self) -> None:
        for node in SEED_NODES:
            assert node.label in ALLOWED_LABELS
        for edge in SEED_EDGES:
            assert edge.relationship in ALLOWED_RELATIONSHIPS


class TestRippleEffect:
    @pytest.mark.asyncio
    async def test_returns_downstream_nodes_and_edges(self) -> None:
        session = FakeSession(
            [
                {
                    "source": "Copper",
                    "relationship": "REFINED_INTO",
                    "target": "Stator Coil",
                    "target_label": "Component",
                    "weight": None,
                },
                {
                    "source": "Stator Coil",
                    "relationship": "REQUIRED_FOR",
                    "target": "EV Battery Manufacturing",
                    "target_label": "Industry",
                    "weight": 0.18,
                },
            ]
        )

        result = await Neo4jSupplyChainRepository(session).ripple_effect("Copper")

        assert [edge.target for edge in result] == ["Stator Coil", "EV Battery Manufacturing"]
        assert result[1].weight == 0.18

    @pytest.mark.asyncio
    async def test_commodity_name_is_a_parameter(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).ripple_effect("Copper")

        query, params = session.queries[0]
        assert "Copper" not in query
        assert params["name"] == "Copper"

    @pytest.mark.asyncio
    async def test_depth_is_validated_because_it_cannot_be_a_parameter(self) -> None:
        """Cypher cannot bind a path length, so the value is checked, not injected."""
        repository = Neo4jSupplyChainRepository(FakeSession())

        with pytest.raises(ValueError, match="depth"):
            await repository.ripple_effect("Copper", max_depth=0)

        with pytest.raises(ValueError, match="depth"):
            await repository.ripple_effect("Copper", max_depth=MAX_RIPPLE_DEPTH + 1)

    @pytest.mark.asyncio
    async def test_depth_appears_in_the_traversal_once_validated(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).ripple_effect("Copper", max_depth=3)

        assert "*1..3" in session.queries[0][0]

    @pytest.mark.asyncio
    async def test_unknown_commodity_returns_nothing(self) -> None:
        repository = Neo4jSupplyChainRepository(FakeSession([]))

        assert await repository.ripple_effect("Unobtainium") == []


class TestExposureQueries:
    @pytest.mark.asyncio
    async def test_lists_filers_exposed_to_a_commodity(self) -> None:
        session = FakeSession(
            [{"filer": "Bridgewater Associates", "cik": "0001350694", "ticker": "NVDA"}]
        )

        exposure = await Neo4jSupplyChainRepository(session).filers_exposed_to("Copper")

        assert exposure[0]["filer"] == "Bridgewater Associates"
        assert session.queries[0][1] == {"name": "Copper"}

    @pytest.mark.asyncio
    async def test_records_a_holding_edge_with_quarter_and_change(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).link_holding(
            HoldingLink(
                filer_cik="1350694",
                filer_name="Bridgewater Associates",
                ticker="NVDA",
                company_name="Nvidia Corp",
                shares=1_200_000,
                quarter="2026-Q2",
                delta_pct=14.0,
            )
        )

        query, params = session.queries[0]
        assert "MERGE" in query
        assert ":HOLDS" in query
        assert params["cik"] == "0001350694"
        assert params["shares"] == 1_200_000
        assert params["quarter"] == "2026-Q2"

    @pytest.mark.asyncio
    async def test_records_company_exposure_to_a_commodity(self) -> None:
        session = FakeSession()

        await Neo4jSupplyChainRepository(session).link_exposure("nvda", "Copper")

        query, params = session.queries[0]
        assert ":EXPOSED_TO" in query
        assert params == {"ticker": "NVDA", "name": "Copper"}


class TestGraphValueObjects:
    def test_node_rejects_an_unknown_label(self) -> None:
        with pytest.raises(ValueError, match="label"):
            GraphNode(label="Wormhole", key="name", value="Copper")

    def test_edge_rejects_an_unknown_relationship(self) -> None:
        with pytest.raises(ValueError, match="relationship"):
            GraphEdge(
                source=GraphNode(label="Commodity", key="name", value="Copper"),
                relationship="TELEPORTS_TO",
                target=GraphNode(label="Industry", key="name", value="Construction"),
            )

    def test_node_and_edge_are_immutable(self) -> None:
        node = GraphNode(label="Commodity", key="name", value="Copper")

        with pytest.raises(AttributeError):
            node.value = "Steel"  # type: ignore[misc]
