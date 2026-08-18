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

# Every entity a collector actually reports needs a node, or clicking it from the risk map
# leads to an empty graph. These four are the ones the running collectors produce.
BRENT = GraphNode(label="Commodity", key="name", value="Brent_Crude")
CRUDE_DELAYED = GraphNode(label="Commodity", key="name", value="WTI_Crude_Delayed")
FBX = GraphNode(label="Commodity", key="name", value="FBX_Global")
BALTIC = GraphNode(label="Commodity", key="name", value="Baltic_Dry_Index")
CORN = GraphNode(label="Commodity", key="name", value="Corn")
SOYBEANS = GraphNode(label="Commodity", key="name", value="Soybeans")

STATOR_COIL = GraphNode(label="Component", key="name", value="Stator Coil")
REBAR = GraphNode(label="Component", key="name", value="Rebar")
BUNKER_FUEL = GraphNode(label="Component", key="name", value="Bunker Fuel")

EV_MANUFACTURING = GraphNode(label="Industry", key="name", value="EV Battery Manufacturing")
CONSTRUCTION = GraphNode(label="Industry", key="name", value="Construction")
OCEAN_FREIGHT = GraphNode(label="Industry", key="name", value="Ocean Freight")
FOOD_MANUFACTURING = GraphNode(label="Industry", key="name", value="Food Manufacturing")
CONSUMER_ELECTRONICS = GraphNode(label="Industry", key="name", value="Consumer Electronics")
RETAIL = GraphNode(label="Industry", key="name", value="Retail Goods")
AIR_FREIGHT = GraphNode(label="Industry", key="name", value="Air Freight")
CHEMICALS = GraphNode(label="Industry", key="name", value="Chemicals and Plastics")
ANIMAL_FEED = GraphNode(label="Industry", key="name", value="Animal Feed")

CONTAINER_SLOT = GraphNode(label="Component", key="name", value="Container Slot")
DRY_BULK_CHARTER = GraphNode(label="Component", key="name", value="Dry Bulk Charter")
DIESEL = GraphNode(label="Component", key="name", value="Diesel and Jet Fuel")

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
    BRENT,
    CRUDE_DELAYED,
    FBX,
    BALTIC,
    CORN,
    SOYBEANS,
    STATOR_COIL,
    REBAR,
    BUNKER_FUEL,
    CONTAINER_SLOT,
    DRY_BULK_CHARTER,
    DIESEL,
    EV_MANUFACTURING,
    CONSTRUCTION,
    OCEAN_FREIGHT,
    FOOD_MANUFACTURING,
    CONSUMER_ELECTRONICS,
    RETAIL,
    AIR_FREIGHT,
    CHEMICALS,
    ANIMAL_FEED,
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
    # Container freight. A lane price is the cost of a slot on a ship, which sits under
    # anything imported: electronics, retail stock, and manufacturing inputs alike.
    GraphEdge(source=FBX, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(source=CONTAINER_SLOT, relationship="REQUIRED_FOR", target=RETAIL),
    GraphEdge(source=CONTAINER_SLOT, relationship="REQUIRED_FOR", target=CONSUMER_ELECTRONICS),
    GraphEdge(
        source=FBX,
        relationship="IMPACTS_COST_OF",
        target=RETAIL,
        properties={"weight": 0.11},
    ),
    GraphEdge(
        source=FBX,
        relationship="IMPACTS_COST_OF",
        target=CONSUMER_ELECTRONICS,
        properties={"weight": 0.06},
    ),
    # Dry bulk freight carries ore, grain, and coal, so it lands on heavy industry and food.
    GraphEdge(source=BALTIC, relationship="REFINED_INTO", target=DRY_BULK_CHARTER),
    GraphEdge(source=DRY_BULK_CHARTER, relationship="REQUIRED_FOR", target=CONSTRUCTION),
    GraphEdge(source=DRY_BULK_CHARTER, relationship="REQUIRED_FOR", target=ANIMAL_FEED),
    GraphEdge(
        source=BALTIC,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.08},
    ),
    GraphEdge(
        source=BALTIC,
        relationship="IMPACTS_COST_OF",
        target=CONSTRUCTION,
        properties={"weight": 0.05},
    ),
    # Brent sets the price of refined fuels outside North America, so it reaches every form
    # of transport and the petrochemicals that plastics are made from.
    GraphEdge(source=BRENT, relationship="REFINED_INTO", target=DIESEL),
    GraphEdge(source=DIESEL, relationship="REQUIRED_FOR", target=AIR_FREIGHT),
    GraphEdge(source=DIESEL, relationship="REQUIRED_FOR", target=OCEAN_FREIGHT),
    GraphEdge(
        source=BRENT,
        relationship="IMPACTS_COST_OF",
        target=AIR_FREIGHT,
        properties={"weight": 0.28},
    ),
    GraphEdge(
        source=BRENT,
        relationship="IMPACTS_COST_OF",
        target=CHEMICALS,
        properties={"weight": 0.19},
    ),
    # The delayed benchmark tracks the same physical barrel as WTI, so it reaches the same
    # industries. Recorded separately because it is collected from a different source and a
    # reader should be able to see which one they are looking at.
    GraphEdge(source=CRUDE_DELAYED, relationship="REFINED_INTO", target=DIESEL),
    GraphEdge(
        source=CRUDE_DELAYED,
        relationship="IMPACTS_COST_OF",
        target=OCEAN_FREIGHT,
        properties={"weight": 0.31},
    ),
    # Feed grains into animal feed and food manufacturing.
    GraphEdge(
        source=CORN,
        relationship="IMPACTS_COST_OF",
        target=ANIMAL_FEED,
        properties={"weight": 0.42},
    ),
    GraphEdge(
        source=SOYBEANS,
        relationship="IMPACTS_COST_OF",
        target=ANIMAL_FEED,
        properties={"weight": 0.27},
    ),
    GraphEdge(
        source=CORN,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.12},
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
