"""The starting graph.

A brand-new database has prices but no idea what they affect, which makes the
ripple view empty and the product hard to evaluate. This module holds a small,
factual starting set: copper into stator coils into electric-vehicle
manufacturing, steel into construction and vehicles, crude oil into freight, and
one fund position linked back to the commodity it is exposed to.

It is data, not logic. Extending the graph means adding entries here; no code
changes are needed, and loading it twice is safe because everything is merged.
"""

from __future__ import annotations

from shadow_cpi.db.neo4j.repository import GraphEdge, GraphNode

# --- Nodes ------------------------------------------------------------------

COPPER = GraphNode(label="Commodity", key="name", value="Copper")
STEEL = GraphNode(label="Commodity", key="name", value="Steel_HRC_US")
CRUDE = GraphNode(label="Commodity", key="name", value="WTI_Crude")
WHEAT = GraphNode(label="Commodity", key="name", value="Wheat")

STATOR_COIL = GraphNode(label="Component", key="name", value="Stator Coil")
REBAR = GraphNode(label="Component", key="name", value="Rebar")
BUNKER_FUEL = GraphNode(label="Component", key="name", value="Bunker Fuel")

EV_MANUFACTURING = GraphNode(label="Industry", key="name", value="EV Battery Manufacturing")
CONSTRUCTION = GraphNode(label="Industry", key="name", value="Construction")
OCEAN_FREIGHT = GraphNode(label="Industry", key="name", value="Ocean Freight")
FOOD_MANUFACTURING = GraphNode(label="Industry", key="name", value="Food Manufacturing")
CONSUMER_ELECTRONICS = GraphNode(label="Industry", key="name", value="Consumer Electronics")

NVIDIA = GraphNode(
    label="Company",
    key="ticker",
    value="NVDA",
    properties={"name": "Nvidia Corp"},
)

BRIDGEWATER = GraphNode(
    label="Filer",
    key="cik",
    value="0001350694",
    properties={"name": "Bridgewater Associates"},
)

SEED_NODES: tuple[GraphNode, ...] = (
    COPPER,
    STEEL,
    CRUDE,
    WHEAT,
    STATOR_COIL,
    REBAR,
    BUNKER_FUEL,
    EV_MANUFACTURING,
    CONSTRUCTION,
    OCEAN_FREIGHT,
    FOOD_MANUFACTURING,
    CONSUMER_ELECTRONICS,
    NVIDIA,
    BRIDGEWATER,
)

# --- Relationships ----------------------------------------------------------
#
# The weight on IMPACTS_COST_OF is the approximate share of that industry's input
# cost attributable to the commodity. It is used to rank which downstream
# industries to surface first, not as a precise economic figure.

SEED_EDGES: tuple[GraphEdge, ...] = (
    # Copper into electric vehicles and electronics.
    GraphEdge(source=COPPER, relationship="REFINED_INTO", target=STATOR_COIL),
    GraphEdge(source=STATOR_COIL, relationship="REQUIRED_FOR", target=EV_MANUFACTURING),
    GraphEdge(
        source=COPPER,
        relationship="IMPACTS_COST_OF",
        target=EV_MANUFACTURING,
        properties={"weight": 0.18},
    ),
    GraphEdge(
        source=COPPER,
        relationship="IMPACTS_COST_OF",
        target=CONSUMER_ELECTRONICS,
        properties={"weight": 0.09},
    ),
    # Steel into construction.
    GraphEdge(source=STEEL, relationship="REFINED_INTO", target=REBAR),
    GraphEdge(source=REBAR, relationship="REQUIRED_FOR", target=CONSTRUCTION),
    GraphEdge(
        source=STEEL,
        relationship="IMPACTS_COST_OF",
        target=CONSTRUCTION,
        properties={"weight": 0.24},
    ),
    # Crude oil into shipping costs.
    GraphEdge(source=CRUDE, relationship="REFINED_INTO", target=BUNKER_FUEL),
    GraphEdge(source=BUNKER_FUEL, relationship="REQUIRED_FOR", target=OCEAN_FREIGHT),
    GraphEdge(
        source=CRUDE,
        relationship="IMPACTS_COST_OF",
        target=OCEAN_FREIGHT,
        properties={"weight": 0.31},
    ),
    # Wheat into food manufacturing.
    GraphEdge(
        source=WHEAT,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.15},
    ),
    # The bridge from fund positions to commodity exposure.
    GraphEdge(
        source=BRIDGEWATER,
        relationship="HOLDS",
        target=NVIDIA,
        properties={"shares": 1_200_000, "quarter": "2026-Q2", "delta_pct": 14.0},
    ),
    GraphEdge(source=NVIDIA, relationship="EXPOSED_TO", target=COPPER),
)
