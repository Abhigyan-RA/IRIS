"""The starting graph.

A brand-new database has prices but no idea what they affect, which makes the
ripple view empty and the product hard to evaluate. This module holds a factual
starting set covering the key commodity chains tracked by this platform:
copper, steel, crude oil, natural gas, wheat, corn, soybeans, container freight,
and dry bulk freight. Each chain is connected to the industries and companies
exposed to it.

It is data, not logic. Extending the graph means adding entries here; no code
changes are needed, and loading it twice is safe because everything is merged.
"""

from __future__ import annotations

from shadow_cpi.db.neo4j.repository import GraphEdge, GraphNode

# --- Commodity nodes --------------------------------------------------------

COPPER = GraphNode(label="Commodity", key="name", value="Copper")
STEEL = GraphNode(label="Commodity", key="name", value="Steel_HRC_US")
CRUDE = GraphNode(label="Commodity", key="name", value="WTI_Crude")
BRENT = GraphNode(label="Commodity", key="name", value="Brent_Crude")
CRUDE_DELAYED = GraphNode(label="Commodity", key="name", value="WTI_Crude_Delayed")
NATURAL_GAS = GraphNode(label="Commodity", key="name", value="Natural_Gas")
WHEAT = GraphNode(label="Commodity", key="name", value="Wheat")
CORN = GraphNode(label="Commodity", key="name", value="Corn")
SOYBEANS = GraphNode(label="Commodity", key="name", value="Soybeans")
GOLD = GraphNode(label="Commodity", key="name", value="Gold")
ALUMINUM = GraphNode(label="Commodity", key="name", value="Aluminum")

# Freight indices — every entity a collector reports needs a node so clicking
# it from the risk map leads to a graph rather than an empty screen.
FBX = GraphNode(label="Commodity", key="name", value="FBX_Global")
BALTIC = GraphNode(label="Commodity", key="name", value="Baltic_Dry_Index")
FBX01 = GraphNode(label="Commodity", key="name", value="FBX01_China_to_North_America_West_Coast")
FBX02 = GraphNode(label="Commodity", key="name", value="FBX02_North_America_West_Coast_to_China")
FBX03 = GraphNode(label="Commodity", key="name", value="FBX03_China_to_North_America_East_Coast")
FBX04 = GraphNode(label="Commodity", key="name", value="FBX04_North_America_East_Coast_to_China")
FBX11 = GraphNode(label="Commodity", key="name", value="FBX11_China_to_Northern_Europe")
FBX12 = GraphNode(label="Commodity", key="name", value="FBX12_Northern_Europe_to_China")
FBX13 = GraphNode(label="Commodity", key="name", value="FBX13_China_to_Mediterranean")
FBX14 = GraphNode(label="Commodity", key="name", value="FBX14_Mediterranean_to_China")
FBX21 = GraphNode(
    label="Commodity", key="name", value="FBX21_North_America_East_Coast_to_Northern_Europe"
)
FBX22 = GraphNode(
    label="Commodity", key="name", value="FBX22_Northern_Europe_to_North_American_East_Coast"
)
FBX24 = GraphNode(label="Commodity", key="name", value="FBX24_Europe_to_South_America_East_Coast")
FBX26 = GraphNode(label="Commodity", key="name", value="FBX26_Europe_to_South_America_West_Coast")

# --- Component nodes --------------------------------------------------------

STATOR_COIL = GraphNode(label="Component", key="name", value="Stator Coil")
REBAR = GraphNode(label="Component", key="name", value="Rebar")
STRUCTURAL_STEEL = GraphNode(label="Component", key="name", value="Structural Steel")
BUNKER_FUEL = GraphNode(label="Component", key="name", value="Bunker Fuel")
CONTAINER_SLOT = GraphNode(label="Component", key="name", value="Container Slot")
DRY_BULK_CHARTER = GraphNode(label="Component", key="name", value="Dry Bulk Charter")
DIESEL = GraphNode(label="Component", key="name", value="Diesel and Jet Fuel")
LNG = GraphNode(label="Component", key="name", value="Liquefied Natural Gas")
ALUMINUM_SHEET = GraphNode(label="Component", key="name", value="Aluminum Sheet")
FLOUR = GraphNode(label="Component", key="name", value="Flour and Starch")
CORN_SYRUP = GraphNode(label="Component", key="name", value="Corn Syrup")
GOLD_BULLION = GraphNode(label="Component", key="name", value="Gold Bullion")
SOYBEAN_MEAL = GraphNode(label="Component", key="name", value="Soybean Meal")
COPPER_WIRE = GraphNode(label="Component", key="name", value="Copper Wire")

# --- Industry nodes ---------------------------------------------------------

EV_MANUFACTURING = GraphNode(label="Industry", key="name", value="EV Battery Manufacturing")
CONSTRUCTION = GraphNode(label="Industry", key="name", value="Construction")
OCEAN_FREIGHT = GraphNode(label="Industry", key="name", value="Ocean Freight")
FOOD_MANUFACTURING = GraphNode(label="Industry", key="name", value="Food Manufacturing")
CONSUMER_ELECTRONICS = GraphNode(label="Industry", key="name", value="Consumer Electronics")
RETAIL = GraphNode(label="Industry", key="name", value="Retail Goods")
AIR_FREIGHT = GraphNode(label="Industry", key="name", value="Air Freight")
CHEMICALS = GraphNode(label="Industry", key="name", value="Chemicals and Plastics")
ANIMAL_FEED = GraphNode(label="Industry", key="name", value="Animal Feed")
POWER_GENERATION = GraphNode(label="Industry", key="name", value="Power Generation")
AEROSPACE = GraphNode(label="Industry", key="name", value="Aerospace and Defense")
AUTOMOTIVE = GraphNode(label="Industry", key="name", value="Automotive Manufacturing")
SEMICONDUCTOR = GraphNode(label="Industry", key="name", value="Semiconductor Manufacturing")
JEWELRY = GraphNode(label="Industry", key="name", value="Jewelry and Luxury Goods")
PACKAGING = GraphNode(label="Industry", key="name", value="Packaging and Containers")
AGRICULTURE_SECTOR = GraphNode(label="Industry", key="name", value="Agricultural Production")
BAKERY = GraphNode(label="Industry", key="name", value="Bakery and Bread Production")
BREWING = GraphNode(label="Industry", key="name", value="Brewing and Distilling")
PASTA = GraphNode(label="Industry", key="name", value="Pasta and Noodles")
ETHANOL = GraphNode(label="Industry", key="name", value="Ethanol and Biofuel")
SWEETENER = GraphNode(label="Industry", key="name", value="Sweetener and Starch Products")
COOKING_OIL = GraphNode(label="Industry", key="name", value="Cooking Oil and Fats")
BIODIESEL = GraphNode(label="Industry", key="name", value="Biodiesel Production")

# --- Company and fund nodes -------------------------------------------------

NVIDIA = GraphNode(label="Company", key="ticker", value="NVDA", properties={"name": "Nvidia Corp"})
BRIDGEWATER = GraphNode(
    label="Filer", key="cik", value="0001350694", properties={"name": "Bridgewater Associates"}
)

# --- Node manifest ----------------------------------------------------------

SEED_NODES: tuple[GraphNode, ...] = (
    COPPER,
    STEEL,
    CRUDE,
    BRENT,
    CRUDE_DELAYED,
    NATURAL_GAS,
    WHEAT,
    CORN,
    SOYBEANS,
    GOLD,
    ALUMINUM,
    FBX,
    BALTIC,
    FBX01,
    FBX02,
    FBX03,
    FBX04,
    FBX11,
    FBX12,
    FBX13,
    FBX14,
    FBX21,
    FBX22,
    FBX24,
    FBX26,
    STATOR_COIL,
    REBAR,
    STRUCTURAL_STEEL,
    BUNKER_FUEL,
    CONTAINER_SLOT,
    DRY_BULK_CHARTER,
    DIESEL,
    LNG,
    ALUMINUM_SHEET,
    FLOUR,
    CORN_SYRUP,
    GOLD_BULLION,
    COPPER_WIRE,
    SOYBEAN_MEAL,
    EV_MANUFACTURING,
    CONSTRUCTION,
    OCEAN_FREIGHT,
    FOOD_MANUFACTURING,
    CONSUMER_ELECTRONICS,
    RETAIL,
    AIR_FREIGHT,
    CHEMICALS,
    ANIMAL_FEED,
    POWER_GENERATION,
    AEROSPACE,
    AUTOMOTIVE,
    SEMICONDUCTOR,
    JEWELRY,
    PACKAGING,
    AGRICULTURE_SECTOR,
    BAKERY,
    BREWING,
    PASTA,
    ETHANOL,
    SWEETENER,
    COOKING_OIL,
    BIODIESEL,
    NVIDIA,
    BRIDGEWATER,
)

# --- Relationships ----------------------------------------------------------
#
# Weights on IMPACTS_COST_OF represent approximate share of input cost.
# Used to rank downstream industries, not as a precise economic figure.

SEED_EDGES: tuple[GraphEdge, ...] = (
    # --- Copper ---
    GraphEdge(source=COPPER, relationship="REFINED_INTO", target=STATOR_COIL),
    GraphEdge(source=COPPER, relationship="REFINED_INTO", target=COPPER_WIRE),
    GraphEdge(source=STATOR_COIL, relationship="REQUIRED_FOR", target=EV_MANUFACTURING),
    GraphEdge(source=COPPER_WIRE, relationship="REQUIRED_FOR", target=CONSUMER_ELECTRONICS),
    GraphEdge(source=COPPER_WIRE, relationship="REQUIRED_FOR", target=SEMICONDUCTOR),
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
    GraphEdge(
        source=COPPER,
        relationship="IMPACTS_COST_OF",
        target=CONSTRUCTION,
        properties={"weight": 0.07},
    ),
    GraphEdge(
        source=COPPER,
        relationship="IMPACTS_COST_OF",
        target=SEMICONDUCTOR,
        properties={"weight": 0.12},
    ),
    # --- Steel ---
    GraphEdge(source=STEEL, relationship="REFINED_INTO", target=REBAR),
    GraphEdge(source=STEEL, relationship="REFINED_INTO", target=STRUCTURAL_STEEL),
    GraphEdge(source=REBAR, relationship="REQUIRED_FOR", target=CONSTRUCTION),
    GraphEdge(source=STRUCTURAL_STEEL, relationship="REQUIRED_FOR", target=AUTOMOTIVE),
    GraphEdge(source=STRUCTURAL_STEEL, relationship="REQUIRED_FOR", target=AEROSPACE),
    GraphEdge(
        source=STEEL,
        relationship="IMPACTS_COST_OF",
        target=CONSTRUCTION,
        properties={"weight": 0.24},
    ),
    GraphEdge(
        source=STEEL, relationship="IMPACTS_COST_OF", target=AUTOMOTIVE, properties={"weight": 0.31}
    ),
    GraphEdge(
        source=STEEL, relationship="IMPACTS_COST_OF", target=AEROSPACE, properties={"weight": 0.14}
    ),
    GraphEdge(
        source=STEEL, relationship="IMPACTS_COST_OF", target=PACKAGING, properties={"weight": 0.09}
    ),
    # --- WTI Crude ---
    GraphEdge(source=CRUDE, relationship="REFINED_INTO", target=BUNKER_FUEL),
    GraphEdge(source=CRUDE, relationship="REFINED_INTO", target=DIESEL),
    GraphEdge(source=BUNKER_FUEL, relationship="REQUIRED_FOR", target=OCEAN_FREIGHT),
    GraphEdge(source=DIESEL, relationship="REQUIRED_FOR", target=AIR_FREIGHT),
    GraphEdge(
        source=CRUDE,
        relationship="IMPACTS_COST_OF",
        target=OCEAN_FREIGHT,
        properties={"weight": 0.31},
    ),
    GraphEdge(
        source=CRUDE,
        relationship="IMPACTS_COST_OF",
        target=AIR_FREIGHT,
        properties={"weight": 0.26},
    ),
    GraphEdge(
        source=CRUDE, relationship="IMPACTS_COST_OF", target=CHEMICALS, properties={"weight": 0.21}
    ),
    GraphEdge(
        source=CRUDE, relationship="IMPACTS_COST_OF", target=AUTOMOTIVE, properties={"weight": 0.08}
    ),
    # --- Brent Crude ---
    GraphEdge(source=BRENT, relationship="REFINED_INTO", target=DIESEL),
    GraphEdge(source=DIESEL, relationship="REQUIRED_FOR", target=OCEAN_FREIGHT),
    GraphEdge(
        source=BRENT,
        relationship="IMPACTS_COST_OF",
        target=AIR_FREIGHT,
        properties={"weight": 0.28},
    ),
    GraphEdge(
        source=BRENT, relationship="IMPACTS_COST_OF", target=CHEMICALS, properties={"weight": 0.19}
    ),
    GraphEdge(
        source=BRENT,
        relationship="IMPACTS_COST_OF",
        target=OCEAN_FREIGHT,
        properties={"weight": 0.29},
    ),
    GraphEdge(
        source=BRENT,
        relationship="IMPACTS_COST_OF",
        target=AGRICULTURE_SECTOR,
        properties={"weight": 0.11},
    ),
    # --- WTI Delayed (same barrel as WTI, different source) ---
    GraphEdge(source=CRUDE_DELAYED, relationship="REFINED_INTO", target=DIESEL),
    GraphEdge(
        source=CRUDE_DELAYED,
        relationship="IMPACTS_COST_OF",
        target=OCEAN_FREIGHT,
        properties={"weight": 0.31},
    ),
    GraphEdge(
        source=CRUDE_DELAYED,
        relationship="IMPACTS_COST_OF",
        target=AIR_FREIGHT,
        properties={"weight": 0.26},
    ),
    # --- Natural Gas ---
    GraphEdge(source=NATURAL_GAS, relationship="REFINED_INTO", target=LNG),
    GraphEdge(source=LNG, relationship="REQUIRED_FOR", target=POWER_GENERATION),
    GraphEdge(
        source=NATURAL_GAS,
        relationship="IMPACTS_COST_OF",
        target=POWER_GENERATION,
        properties={"weight": 0.35},
    ),
    GraphEdge(
        source=NATURAL_GAS,
        relationship="IMPACTS_COST_OF",
        target=CHEMICALS,
        properties={"weight": 0.22},
    ),
    GraphEdge(
        source=NATURAL_GAS,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.09},
    ),
    GraphEdge(
        source=NATURAL_GAS,
        relationship="IMPACTS_COST_OF",
        target=AUTOMOTIVE,
        properties={"weight": 0.08},
    ),
    # --- Wheat ---
    GraphEdge(source=WHEAT, relationship="REFINED_INTO", target=FLOUR),
    GraphEdge(source=FLOUR, relationship="REQUIRED_FOR", target=FOOD_MANUFACTURING),
    GraphEdge(
        source=WHEAT,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.15},
    ),
    GraphEdge(
        source=WHEAT,
        relationship="IMPACTS_COST_OF",
        target=ANIMAL_FEED,
        properties={"weight": 0.18},
    ),
    GraphEdge(
        source=WHEAT, relationship="IMPACTS_COST_OF", target=BAKERY, properties={"weight": 0.55}
    ),
    GraphEdge(
        source=WHEAT, relationship="IMPACTS_COST_OF", target=BREWING, properties={"weight": 0.22}
    ),
    GraphEdge(
        source=WHEAT, relationship="IMPACTS_COST_OF", target=PASTA, properties={"weight": 0.48}
    ),
    GraphEdge(
        source=WHEAT, relationship="IMPACTS_COST_OF", target=PACKAGING, properties={"weight": 0.04}
    ),
    GraphEdge(source=FLOUR, relationship="REQUIRED_FOR", target=BAKERY),
    GraphEdge(source=FLOUR, relationship="REQUIRED_FOR", target=PASTA),
    # --- Corn ---
    GraphEdge(source=CORN, relationship="REFINED_INTO", target=CORN_SYRUP),
    GraphEdge(source=CORN_SYRUP, relationship="REQUIRED_FOR", target=FOOD_MANUFACTURING),
    GraphEdge(
        source=CORN, relationship="IMPACTS_COST_OF", target=ANIMAL_FEED, properties={"weight": 0.42}
    ),
    GraphEdge(
        source=CORN,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.12},
    ),
    GraphEdge(
        source=CORN,
        relationship="IMPACTS_COST_OF",
        target=AGRICULTURE_SECTOR,
        properties={"weight": 0.28},
    ),
    GraphEdge(
        source=CORN, relationship="IMPACTS_COST_OF", target=ETHANOL, properties={"weight": 0.71}
    ),
    GraphEdge(
        source=CORN, relationship="IMPACTS_COST_OF", target=SWEETENER, properties={"weight": 0.38}
    ),
    # --- Soybeans ---
    GraphEdge(source=SOYBEANS, relationship="REFINED_INTO", target=SOYBEAN_MEAL),
    GraphEdge(source=SOYBEAN_MEAL, relationship="REQUIRED_FOR", target=ANIMAL_FEED),
    GraphEdge(
        source=SOYBEANS,
        relationship="IMPACTS_COST_OF",
        target=ANIMAL_FEED,
        properties={"weight": 0.27},
    ),
    GraphEdge(
        source=SOYBEANS,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.08},
    ),
    GraphEdge(
        source=SOYBEANS,
        relationship="IMPACTS_COST_OF",
        target=CHEMICALS,
        properties={"weight": 0.06},
    ),
    GraphEdge(
        source=SOYBEANS,
        relationship="IMPACTS_COST_OF",
        target=COOKING_OIL,
        properties={"weight": 0.55},
    ),
    GraphEdge(
        source=SOYBEANS,
        relationship="IMPACTS_COST_OF",
        target=BIODIESEL,
        properties={"weight": 0.45},
    ),
    # --- Gold ---
    GraphEdge(source=GOLD, relationship="REFINED_INTO", target=GOLD_BULLION),
    GraphEdge(source=GOLD_BULLION, relationship="REQUIRED_FOR", target=JEWELRY),
    GraphEdge(
        source=GOLD, relationship="IMPACTS_COST_OF", target=JEWELRY, properties={"weight": 0.65}
    ),
    GraphEdge(
        source=GOLD,
        relationship="IMPACTS_COST_OF",
        target=SEMICONDUCTOR,
        properties={"weight": 0.04},
    ),
    GraphEdge(
        source=GOLD, relationship="IMPACTS_COST_OF", target=AEROSPACE, properties={"weight": 0.03}
    ),
    # --- Aluminum ---
    GraphEdge(source=ALUMINUM, relationship="REFINED_INTO", target=ALUMINUM_SHEET),
    GraphEdge(source=ALUMINUM_SHEET, relationship="REQUIRED_FOR", target=AUTOMOTIVE),
    GraphEdge(source=ALUMINUM_SHEET, relationship="REQUIRED_FOR", target=AEROSPACE),
    GraphEdge(source=ALUMINUM_SHEET, relationship="REQUIRED_FOR", target=PACKAGING),
    GraphEdge(
        source=ALUMINUM,
        relationship="IMPACTS_COST_OF",
        target=AUTOMOTIVE,
        properties={"weight": 0.14},
    ),
    GraphEdge(
        source=ALUMINUM,
        relationship="IMPACTS_COST_OF",
        target=AEROSPACE,
        properties={"weight": 0.22},
    ),
    GraphEdge(
        source=ALUMINUM,
        relationship="IMPACTS_COST_OF",
        target=PACKAGING,
        properties={"weight": 0.38},
    ),
    GraphEdge(
        source=ALUMINUM,
        relationship="IMPACTS_COST_OF",
        target=CONSUMER_ELECTRONICS,
        properties={"weight": 0.07},
    ),
    # --- FBX Global container freight ---
    GraphEdge(source=FBX, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(source=CONTAINER_SLOT, relationship="REQUIRED_FOR", target=RETAIL),
    GraphEdge(source=CONTAINER_SLOT, relationship="REQUIRED_FOR", target=CONSUMER_ELECTRONICS),
    GraphEdge(source=CONTAINER_SLOT, relationship="REQUIRED_FOR", target=FOOD_MANUFACTURING),
    GraphEdge(
        source=FBX, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.11}
    ),
    GraphEdge(
        source=FBX,
        relationship="IMPACTS_COST_OF",
        target=CONSUMER_ELECTRONICS,
        properties={"weight": 0.06},
    ),
    GraphEdge(
        source=FBX,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.05},
    ),
    GraphEdge(
        source=FBX, relationship="IMPACTS_COST_OF", target=AUTOMOTIVE, properties={"weight": 0.04}
    ),
    # --- FBX individual lanes (all feed into the same downstream industries as the index) ---
    GraphEdge(source=FBX01, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX01, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.09}
    ),
    GraphEdge(
        source=FBX01,
        relationship="IMPACTS_COST_OF",
        target=CONSUMER_ELECTRONICS,
        properties={"weight": 0.07},
    ),
    GraphEdge(source=FBX02, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX02, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.04}
    ),
    GraphEdge(
        source=FBX02, relationship="IMPACTS_COST_OF", target=AUTOMOTIVE, properties={"weight": 0.03}
    ),
    GraphEdge(
        source=FBX02,
        relationship="IMPACTS_COST_OF",
        target=AGRICULTURE_SECTOR,
        properties={"weight": 0.02},
    ),
    GraphEdge(source=FBX03, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX03, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.09}
    ),
    GraphEdge(
        source=FBX03,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.05},
    ),
    GraphEdge(source=FBX04, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX04, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.03}
    ),
    GraphEdge(
        source=FBX04, relationship="IMPACTS_COST_OF", target=CHEMICALS, properties={"weight": 0.03}
    ),
    GraphEdge(
        source=FBX04, relationship="IMPACTS_COST_OF", target=AUTOMOTIVE, properties={"weight": 0.02}
    ),
    GraphEdge(source=FBX11, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX11, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.08}
    ),
    GraphEdge(
        source=FBX11,
        relationship="IMPACTS_COST_OF",
        target=CONSUMER_ELECTRONICS,
        properties={"weight": 0.06},
    ),
    GraphEdge(source=FBX12, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX12, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.03}
    ),
    GraphEdge(source=FBX13, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX13, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.07}
    ),
    GraphEdge(source=FBX14, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX14, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.03}
    ),
    GraphEdge(source=FBX21, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX21, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.04}
    ),
    GraphEdge(source=FBX22, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX22, relationship="IMPACTS_COST_OF", target=RETAIL, properties={"weight": 0.04}
    ),
    GraphEdge(source=FBX24, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX24,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.04},
    ),
    GraphEdge(source=FBX26, relationship="REFINED_INTO", target=CONTAINER_SLOT),
    GraphEdge(
        source=FBX26,
        relationship="IMPACTS_COST_OF",
        target=FOOD_MANUFACTURING,
        properties={"weight": 0.04},
    ),
    # --- Baltic Dry Index (dry bulk: ore, grain, coal) ---
    GraphEdge(source=BALTIC, relationship="REFINED_INTO", target=DRY_BULK_CHARTER),
    GraphEdge(source=DRY_BULK_CHARTER, relationship="REQUIRED_FOR", target=CONSTRUCTION),
    GraphEdge(source=DRY_BULK_CHARTER, relationship="REQUIRED_FOR", target=ANIMAL_FEED),
    GraphEdge(source=DRY_BULK_CHARTER, relationship="REQUIRED_FOR", target=POWER_GENERATION),
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
    GraphEdge(
        source=BALTIC,
        relationship="IMPACTS_COST_OF",
        target=POWER_GENERATION,
        properties={"weight": 0.06},
    ),
    GraphEdge(
        source=BALTIC,
        relationship="IMPACTS_COST_OF",
        target=AGRICULTURE_SECTOR,
        properties={"weight": 0.07},
    ),
    # --- Fund exposure bridge ---
    GraphEdge(
        source=BRIDGEWATER,
        relationship="HOLDS",
        target=NVIDIA,
        properties={"shares": 1_200_000, "quarter": "2026-Q2", "delta_pct": 14.0},
    ),
    GraphEdge(source=NVIDIA, relationship="EXPOSED_TO", target=COPPER),
)
