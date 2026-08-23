# Shadow CPI — Real-Time Inflation Intelligence Platform

> **Track what official CPI misses.** Shadow CPI scrapes commodity prices, freight indices, and institutional fund holdings daily using Bright Data Scraper Studio, stores them in a time-series + graph database, and surfaces anomalies through an AI-powered dashboard and MCP server.

---

## Table of Contents

- [The Problem](#the-problem)
- [What Shadow CPI Does](#what-shadow-cpi-does)
- [How Bright Data Scraper Studio Is Used](#how-bright-data-scraper-studio-is-used)
- [Scraping Workflow Diagram](#scraping-workflow-diagram)
- [Self-Healing Workflow Diagram](#self-healing-workflow-diagram)
- [System Architecture](#system-architecture)
- [Structured Output Examples](#structured-output-examples)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Setup and Installation](#setup-and-installation)
- [Running the Application](#running-the-application)
- [Data Sources](#data-sources)
- [API Endpoints](#api-endpoints)
- [MCP Server (AI Agent Interface)](#mcp-server-ai-agent-interface)
- [Testing](#testing)
- [AI Disclosure](#ai-disclosure)

---

## The Problem

Official inflation data (CPI) is published **monthly** and describes prices from **weeks ago**. Traders, analysts, and supply-chain managers need to know what's getting expensive **today** — not what was expensive a month ago.

The public data exists: ocean freight rates update daily, metal spot prices move by the minute, energy benchmarks publish hourly. But it's scattered across dozens of sites that actively block automated readers with CAPTCHAs, IP bans, and JavaScript challenges.

## What Shadow CPI Does

Shadow CPI watches the underlying prices **every day** from ~15 public sources:

- **Energy**: WTI Crude, Brent Crude, Natural Gas (Henry Hub)
- **Metals**: Copper, Gold, Aluminum, Steel (HRC)
- **Freight**: Freightos Baltic Index (12 trade lanes), Baltic Dry Index
- **Agriculture**: Wheat, Corn, Soybeans (CBOT futures), USDA grain prices
- **Institutional Holdings**: SEC 13F filings + WhaleWisdom fund enrichment (20+ major funds)

It answers two questions:

1. **What is getting more expensive?** — Daily price tracking with anomaly detection
2. **What does that affect downstream?** — Neo4j supply-chain graph traces ripple effects

Two interfaces serve the same data:

- A **Next.js dashboard** for analysts (risk map, ripple chain, institutional view, copilot)
- An **MCP server** so AI agents and IDEs can query it programmatically

---

## How Bright Data Scraper Studio Is Used

**This project uses Bright Data Scraper Studio as its core scraping infrastructure.** Every commercial data source that blocks automated readers is collected through a custom Scraper Studio collector.

### Creating a Custom Scraper

Scrapers are created from the terminal with one command — no code, no CSS selectors:

```bash
# Create a copper price scraper
npx -p @brightdata/cli bdata scraper create \
  https://www.investing.com/commodities/copper \
  "Extract the current copper futures price in USD per pound and its daily percent change"

# Output: c_mswnopw72dyj64c7s3  (stable collector ID)
```

```bash
# Create a WhaleWisdom institutional holdings scraper
npx -p @brightdata/cli bdata scraper create \
  "https://whalewisdom.com/filer/bridgewater-associates-lp#tabholdings_tab" \
  "Extract institutional fund holdings data: fund name, stock ticker symbol, shares held, market value in USD, percent of portfolio, quarterly change in shares, and stock name"

# Output: c_mt2abc123xyz  (stable collector ID)
```

The AI agent inside Scraper Studio reads the page, understands the prompt, and writes the scraping code automatically. The collector ID is a **stable handle** — it never changes, even when the scraper is repaired after a site redesign.

### What Scraper Studio Provides

| Capability                    | How We Use It                                                             |
| ----------------------------- | ------------------------------------------------------------------------- |
| **AI-generated scrapers**     | One sentence creates a complete scraper — no selectors to write           |
| **Unblocking infrastructure** | Handles CAPTCHAs, IP rotation, browser fingerprinting automatically       |
| **Structured JSON output**    | Every scraper returns clean, typed JSON matching our schema               |
| **Self-healing API**          | When a site redesigns, we trigger repair with a description of what broke |
| **Stable collector IDs**      | Schedules and integrations never break — same ID before and after repair  |

### Custom Scrapers Built for This Project

| Scraper                   | Target Site                            | Data Extracted                                |
| ------------------------- | -------------------------------------- | --------------------------------------------- |
| `lme_copper_scraper`      | investing.com/commodities/copper       | Price, daily % change, high/low               |
| `fbx_scraper`             | fbx.freightos.com                      | Global index + 12 trade lane prices           |
| `baltic_dry_scraper`      | tradingeconomics.com                   | Baltic Dry Index value + % change             |
| `oilprice_scraper`        | oilprice.com                           | WTI, Brent, refined product prices            |
| `gold_scraper`            | investing.com/commodities/gold         | Gold price/oz + daily change                  |
| `aluminum_scraper`        | investing.com/commodities/aluminum     | Aluminum price/ton + daily change             |
| `natural_gas_scraper`     | investing.com/commodities/natural-gas  | Henry Hub price/MMBtu                         |
| `wheat_scraper`           | investing.com/commodities/us-wheat     | CBOT wheat futures                            |
| `corn_scraper`            | investing.com/commodities/us-corn      | CBOT corn futures                             |
| `soybeans_scraper`        | investing.com/commodities/soybeans     | CBOT soybean futures                          |
| `steel_scraper`           | investing.com/commodities/us-hrc-steel | US HRC steel price                            |
| `whalewisdom_13f_scraper` | whalewisdom.com                        | Fund holdings, sector allocation, portfolio % |

---

## Scraping Workflow Diagram

```
+------------------+     +------------------------+     +-------------------+
|                  |     |                        |     |                   |
|   SCHEDULER      |     |  BRIGHT DATA SCRAPER   |     |   AI (GEMINI)     |
|   (cron-based)   |     |  STUDIO API            |     |                   |
|                  |     |                        |     |                   |
+--------+---------+     +----------+-------------+     +--------+----------+
         |                          |                             |
         |  1. Trigger collector    |                             |
         +------------------------->|                             |
         |                          |                             |
         |                          |  2. Scraper Studio runs     |
         |                          |     AI-generated code on    |
         |                          |     unblocking infra        |
         |                          |     (CAPTCHA solve, IP      |
         |                          |      rotation, rendering)   |
         |                          |                             |
         |  3. Return structured    |                             |
         |     JSON rows            |                             |
         |<-------------------------+                             |
         |                          |                             |
         |  4. Validate against     |                             |
         |     pydantic schema      |                             |
         +------------------------------------------>             |
         |                          |               |             |
         |                          |  5. Normalize |             |
         |                          |     & extract |             |
         |                          |     prices    |             |
         |                          |               +------------>|
         |                          |               |  6. AI      |
         |                          |               |  normalizes |
         |                          |               |  text to    |
         |                          |               |  Decimal    |
         |<---------------------------------------------------------+
         |                                                        |
         |  7. Store in TimescaleDB                               |
         |     (price history)                                    |
         |                                                        |
         |  8. Store relationships                                |
         |     in Neo4j (supply chain graph)                      |
         |                                                        |
         |  9. Record health event                                |
         |     (pipeline-health feed)                             |
         v                                                        v

+---------------------------+     +-------------------------------+
|      TIMESCALE DB         |     |          NEO4J                |
|  (time-series prices,     |     |  (supply-chain graph:         |
|   institutional holdings) |     |   commodity -> product ->     |
|                           |     |   sector -> fund exposure)    |
+---------------------------+     +-------------------------------+
```

### Detailed Flow for a Single Scraper Run

```
                    +-----------------------+
                    |   Scheduler triggers   |
                    |   source "lme_copper"  |
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    | POST /dca/trigger     |
                    | ?collector=c_msw...   |
                    | body: {"url": "..."}  |
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    | Bright Data runs the  |
                    | collector on its own  |
                    | browser fleet with    |
                    | anti-detection        |
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    | GET /dca/get_result   |
                    | ?response_id=d2t...   |
                    | (poll until ready)    |
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    | Returns JSON:         |
                    | [{"price": {"value":  |
                    |   "4.52"},            |
                    |   "price_change_      |
                    |    percent": "+1.2%"}]|
                    +-----------+-----------+
                                |
                                v
                    +-----------------------+
                    | Health check:         |
                    | Can price be found    |
                    | at declared paths?    |
                    +---+---------------+---+
                        |               |
                   YES  |               |  NO
                        v               v
              +-----------+    +------------------+
              | Parse &   |    | SELF-HEAL FLOW   |
              | store in  |    | (see next        |
              | database  |    |  diagram)        |
              +-----------+    +------------------+
```

---

## Self-Healing Workflow Diagram

When a target site redesigns its page, the scraper stops finding values. Shadow CPI **automatically detects and repairs this** using Bright Data's self-healing API:

```
+-------------------------------------------------------------------+
|                    SELF-HEALING PIPELINE                           |
+-------------------------------------------------------------------+

     Site Redesign Detected
     (price not found at declared paths)
                |
                v
+-------------------------------+
| [WARNING] Site reads          |
| differently. Missing: price   |
| at paths price.value, price   |
+---------------+---------------+
                |
                v
+-------------------------------+
| Gemini AI writes a plain-     |
| language description of       |
| what broke:                   |
|                               |
| "The price field is no longer |
|  at .price.value — the page   |
|  now nests it under           |
|  .market_data.last_price"     |
+---------------+---------------+
                |
                v
+-------------------------------+
| POST /dca/collectors/{id}/    |
|      refactor_template        |
| body: {"prompt": "..."}       |
|                               |
| Scraper Studio AI rewrites    |
| the scraper's parsing code    |
+---------------+---------------+
                |
                v
+-------------------------------+
| Poll refactor_template/       |
| progress until:               |
| status = "awaiting_approval"  |
+---------------+---------------+
                |
                v
+-------------------------------+
| [AUTO-HEALING] Accept draft   |
| POST /dca/collectors/{id}/    |
|      resume_automation_job    |
| body: {"message": true,       |
|        "auto_save": true}     |
+---------------+---------------+
                |
                v
+-------------------------------+
| Re-run collector with same    |
| stable ID (c_msw...)          |
+---------------+---------------+
                |
          +-----+-----+
          |           |
     SUCCESS      FAILURE
          |           |
          v           v
+-------------+ +------------------+
| [RESOLVED]  | | [FAILED]         |
| Values are  | | Manual review    |
| back. Store | | needed. Event    |
| normally.   | | logged.          |
+-------------+ +------------------+

KEY INSIGHT: The collector ID never changes through any of this.
Schedules, API integrations, and the dashboard all keep working.
No CSS selectors are involved — repair is a sentence, not code.
```

### Why This Matters

Traditional scrapers break when a site changes a CSS class or restructures its DOM. Fixing them requires:

1. A developer to notice the break
2. Inspect the new page structure
3. Rewrite selectors
4. Test and deploy

Shadow CPI's approach:

1. **Automatic detection** — health check spots missing values instantly
2. **AI diagnosis** — Gemini describes what changed in plain language
3. **AI repair** — Scraper Studio rewrites its own parsing code
4. **Zero downtime** — same collector ID, no redeployment needed
5. **Full observability** — every step logged to pipeline-health feed

---

## System Architecture

```
+-------------------------------------------------------------------+
|                         SHADOW CPI                                 |
+-------------------------------------------------------------------+
|                                                                    |
|  +------------------+    +------------------+    +---------------+ |
|  |  DATA SOURCES    |    |   BACKEND        |    |  FRONTENDS    | |
|  |                  |    |   (FastAPI)       |    |               | |
|  |  Bright Data     |    |                  |    |  Next.js      | |
|  |  Scraper Studio  +--->+  Ingestion       +--->+  Dashboard    | |
|  |  (12 scrapers)   |    |  Orchestration   |    |               | |
|  |                  |    |  AI Services     |    |  MCP Server   | |
|  |  Official APIs   +--->+  REST API        +--->+  (for AI      | |
|  |  (EIA, USDA,     |    |                  |    |   agents)     | |
|  |   SEC EDGAR)     |    +--------+---------+    +---------------+ |
|  +------------------+             |                                |
|                                   v                                |
|                    +-----------------------------+                  |
|                    |        DATABASES            |                  |
|                    |                             |                  |
|                    |  TimescaleDB  |  Neo4j      |                  |
|                    |  (prices,     |  (supply    |                  |
|                    |   holdings)   |   chain)    |                  |
|                    |               |             |                  |
|                    |  Redis (rate limiting)      |                  |
|                    +-----------------------------+                  |
+-------------------------------------------------------------------+
```

---

## Structured Output Examples

### Commodity Price Scraper Output (Bright Data Scraper Studio)

When the `lme_copper_scraper` collector runs against investing.com:

```json
[
  {
    "price": {
      "value": "4.5230"
    },
    "price_change_percent": "+1.82%",
    "high": "4.5510",
    "low": "4.4380"
  }
]
```

### Freight Index Scraper Output (FBX — Multiple Trade Lanes)

The `fbx_scraper` returns the global index plus each trade lane:

```json
[
  {
    "fbx_global_index_value": { "value": "2,481" },
    "fbx_global_index_percent_change": "-0.3%",
    "product_page_url": "/fbx-03/china-to-north-america-east-coast",
    "fbx01_value": { "value": "3,127" }
  },
  {
    "fbx_global_index_value": { "value": "2,481" },
    "fbx_global_index_percent_change": "-0.3%",
    "product_page_url": "/fbx-11/china-to-north-europe",
    "fbx01_value": { "value": "4,592" }
  },
  {
    "fbx_global_index_value": { "value": "2,481" },
    "fbx_global_index_percent_change": "-0.3%",
    "product_page_url": "/fbx-22/north-europe-to-north-america-east-coast",
    "fbx01_value": { "value": "1,843" }
  }
]
```

### WhaleWisdom Institutional Holdings Output (Bright Data Scraper Studio)

The `whalewisdom_13f_scraper` extracts complete fund portfolios from WhaleWisdom's public pages:

```json
[
  {
    "holdings": [
      {
        "ticker": "AAPL",
        "sector": "INFORMATION TECHNOLOGY",
        "shares_held": 227917808,
        "market_value": 65950296923,
        "percent_of_portfolio": "22.04%",
        "previous_percent_of_portfolio": "21.99%",
        "change_in_shares": "No Change"
      },
      {
        "ticker": "AXP",
        "sector": "FINANCE",
        "shares_held": 151610700,
        "market_value": 51282319275,
        "percent_of_portfolio": "17.14%",
        "previous_percent_of_portfolio": "17.43%",
        "change_in_shares": "No Change"
      },
      {
        "ticker": "GOOGL",
        "sector": "COMMUNICATIONS",
        "shares_held": 78791167,
        "market_value": 28157599351,
        "percent_of_portfolio": "9.41%",
        "previous_percent_of_portfolio": "5.93%",
        "change_in_shares": "24,541,369"
      },
      {
        "ticker": "BAC",
        "sector": "FINANCE",
        "shares_held": 483394015,
        "market_value": 27543790975,
        "percent_of_portfolio": "9.20%",
        "previous_percent_of_portfolio": "9.52%",
        "change_in_shares": "-30,230,150"
      },
      {
        "ticker": "CVX",
        "sector": "ENERGY",
        "shares_held": 84375856,
        "market_value": 13986141890,
        "percent_of_portfolio": "4.67%",
        "previous_percent_of_portfolio": "6.64%",
        "change_in_shares": "No Change"
      }
    ],
    "input": {
      "url": "https://whalewisdom.com/filer/berkshire-hathaway-inc"
    }
  }
]
```

This structured output is collected for **20+ major institutional funds** including:

- Berkshire Hathaway, Bridgewater Associates, D.E. Shaw
- Fidelity, Franklin Resources, Invesco
- Millennium Management, Northern Trust, Point72
- State Street, T. Rowe Price

---

## Project Structure

```
shadow-cpi/
├── backend/                        # FastAPI Python service (core engine)
│   ├── src/shadow_cpi/
│   │   ├── ai/                     # AI services powered by Google Gemini
│   │   │   ├── gemini.py           # Gemini API client with retry & token mgmt
│   │   │   ├── copilot.py          # Natural-language Q&A over stored data
│   │   │   ├── page_extractor.py   # AI reads values from raw page HTML
│   │   │   ├── normalizer.py       # AI converts "$4,520.75" -> Decimal
│   │   │   ├── anomaly.py          # Detects unusual price movements
│   │   │   ├── narrator.py         # Generates human explanations of moves
│   │   │   ├── explainer.py        # Explains supply-chain impact
│   │   │   ├── instruction_drafter.py  # Writes healing prompts for broken scrapers
│   │   │   ├── prompts.py          # Centralized prompt templates
│   │   │   └── protocols.py        # AI service interfaces (for testing)
│   │   │
│   │   ├── api/                    # REST API layer
│   │   │   ├── app.py              # FastAPI app factory with CORS, headers
│   │   │   ├── main.py             # Uvicorn entry point
│   │   │   ├── dependencies.py     # Dependency injection container
│   │   │   ├── rate_limit.py       # Per-IP rate limiting via Redis
│   │   │   ├── security.py         # Secret comparison, auth headers
│   │   │   ├── freshness.py        # Data staleness detection
│   │   │   └── routes/
│   │   │       ├── prices.py       # GET /api/risk-map, /api/commodities/{}/trend
│   │   │       ├── graph.py        # GET /api/graph/ripple/{commodity}
│   │   │       ├── institutional.py # GET /api/institutional/* endpoints
│   │   │       ├── copilot.py      # POST /api/copilot/ask
│   │   │       ├── pipeline.py     # GET /api/pipeline-health (+ SSE stream)
│   │   │       └── health.py       # GET /health (liveness)
│   │   │
│   │   ├── db/                     # Database layer (dual-database)
│   │   │   ├── protocols.py        # Repository interfaces (no impl dependency)
│   │   │   ├── prepare.py          # Schema creation & migration runner
│   │   │   ├── smoke_check.py      # Integration test for real DB connections
│   │   │   ├── timescale/          # TimescaleDB (time-series prices + holdings)
│   │   │   │   ├── repositories.py # CRUD for prices, holdings, health events
│   │   │   │   ├── executor.py     # Connection pool & query execution
│   │   │   │   ├── migrator.py     # SQL migration runner
│   │   │   │   └── migrations/     # SQL schema files (001, 002, 003...)
│   │   │   └── neo4j/              # Neo4j (supply-chain knowledge graph)
│   │   │       ├── repository.py   # Graph queries: ripple, exposure, paths
│   │   │       ├── session.py      # Driver session management
│   │   │       └── seed.py         # Initial graph: commodities -> products -> sectors
│   │   │
│   │   ├── ingestion/              # Data collection engine
│   │   │   ├── registry.py         # Source discovery via @decorator registration
│   │   │   ├── base.py             # Base classes: IngestionContext, IngestionResult
│   │   │   ├── page_fetcher.py     # Direct HTTP page fetcher (government sites)
│   │   │   ├── changes.py          # Calculates daily/weekly % changes from history
│   │   │   ├── repair.py           # Instruction drafting for self-healing
│   │   │   ├── http.py             # HTTP client abstraction with retries
│   │   │   ├── brightdata/         # >>> BRIGHT DATA SCRAPER STUDIO INTEGRATION <<<
│   │   │   │   ├── collectors.py   # 12 custom scraper definitions (ScrapedSource)
│   │   │   │   ├── studio.py       # Scraper Studio API client (trigger/poll/heal)
│   │   │   │   ├── studio_runner.py # Self-healing run loop (run -> check -> heal -> retry)
│   │   │   │   ├── self_heal.py    # Page-fetcher healing variant (fetch -> AI read -> heal)
│   │   │   │   ├── health.py       # Payload health checks (are values at expected paths?)
│   │   │   │   └── whalewisdom.py  # WhaleWisdom fund holdings scraper (institutional)
│   │   │   └── official/           # Sources with official APIs (no scraping needed)
│   │   │       ├── eia.py          # EIA petroleum spot prices (free API)
│   │   │       ├── eia_gas.py      # EIA natural gas prices
│   │   │       ├── usda_mars.py    # USDA grain prices (free API)
│   │   │       ├── sec_edgar.py    # SEC EDGAR 13F filings (authoritative holdings)
│   │   │       └── _percent.py     # Shared percentage parsing utility
│   │   │
│   │   ├── orchestration/          # Scheduling and execution
│   │   │   ├── scheduler.py        # Cron-like scheduler (respects publish frequency)
│   │   │   └── collector.py        # Runs sources, writes results, records health
│   │   │
│   │   ├── mcp_server/             # Model Context Protocol server (AI agent interface)
│   │   │   ├── server.py           # 5 tools: trends, supply chain, holders, freshness, ask
│   │   │   └── main.py             # stdio entry point for IDE integration
│   │   │
│   │   ├── shared/                 # Domain models & validation
│   │   │   ├── models.py           # Pydantic models: CommodityPrice, Holdings, Events
│   │   │   ├── enums.py            # Sector, IngestionMethod, PipelineEventType
│   │   │   └── validation.py       # Schema validation utilities
│   │   │
│   │   ├── tooling/                # Developer tooling
│   │   │   └── no_emoji.py         # Enforces text labels over emoji in codebase
│   │   │
│   │   ├── config.py               # All configuration from env vars (secrets masked)
│   │   ├── wiring.py               # Dependency wiring (builds real implementations)
│   │   ├── collect.py              # CLI: python -m shadow_cpi.collect
│   │   └── runtime.py              # Runtime checks and startup validation
│   │
│   ├── tests/                      # 35+ test files, >80% coverage enforced
│   └── pyproject.toml              # Python project config (dependencies, tools)
│
├── apps/web/                       # Next.js 15 dashboard (React, TypeScript, Tailwind)
│   ├── app/                        # App Router pages
│   │   └── (dashboard)/
│   │       ├── risk-map/           # Main price monitoring view
│   │       ├── ripple/             # Supply-chain impact explorer
│   │       ├── institutional/      # Fund holdings tracker
│   │       ├── copilot/            # AI Q&A interface
│   │       └── pipeline-health/    # Collector status monitor
│   │
│   ├── components/
│   │   ├── risk-map/               # Price heatmap, index summary, top movers, world map
│   │   │   ├── RiskMapPanel.tsx    # Main risk map container
│   │   │   ├── IndexSummary.tsx    # Aggregate inflation index
│   │   │   ├── TopMovers.tsx       # Biggest daily price changes
│   │   │   ├── LanePrices.tsx      # Freight trade lane prices
│   │   │   └── WorldMap.tsx        # Geographic price visualization
│   │   │
│   │   ├── ripple/                 # Supply chain impact visualization
│   │   │   ├── RippleChain.tsx     # Graph traversal: commodity -> product -> fund
│   │   │   ├── SelectedNode.tsx    # Detail panel for selected graph node
│   │   │   └── ExposedFunds.tsx    # Funds exposed to a commodity price move
│   │   │
│   │   ├── institutional/          # Institutional investor tracking
│   │   │   ├── InstitutionalOverviewPanel.tsx  # Fund list, top stocks, sector breakdown
│   │   │   ├── FilerHoldingsPanel.tsx          # Single fund's full portfolio
│   │   │   ├── HoldersTable.tsx    # Who holds a given stock
│   │   │   └── TickerPicker.tsx    # Stock search/select component
│   │   │
│   │   ├── shell/                  # App chrome & navigation
│   │   │   ├── AppShell.tsx        # Layout wrapper with sidebar
│   │   │   ├── NavRail.tsx         # Sidebar navigation
│   │   │   ├── UtcClock.tsx        # Real-time UTC clock
│   │   │   ├── LivePill.tsx        # Connection status indicator
│   │   │   └── ThemeToggle.tsx     # Dark/light mode switch
│   │   │
│   │   ├── copilot/               # AI assistant chat interface
│   │   │   └── CopilotConversation.tsx  # Chat with citations from stored data
│   │   │
│   │   ├── pipeline/              # Data pipeline monitoring
│   │   │   ├── CollectorHealth.tsx # Status of each data source
│   │   │   └── AuditLog.tsx       # Historical run log with outcomes
│   │   │
│   │   ├── feedback/              # Error handling & notifications
│   │   │   ├── Toast.tsx          # Transient notifications
│   │   │   └── FailureNotice.tsx  # Persistent error explanations
│   │   │
│   │   ├── charts/                # Data visualization
│   │   │   └── Sparkline.tsx      # Inline price trend charts
│   │   │
│   │   └── primitives/            # Design system base components
│   │       ├── MetricCard.tsx     # Numeric display with label & delta
│   │       ├── Panel.tsx          # Section container with header
│   │       ├── Delta.tsx          # +/- percentage change indicator
│   │       └── StatusDot.tsx      # Colored status indicator
│   │
│   ├── lib/                       # Shared utilities
│   │   ├── api.ts                 # Type-safe API client with error handling
│   │   ├── failures.ts            # Failure classification & user-facing messages
│   │   └── filers.ts              # Fund name normalization
│   │
│   ├── e2e/                       # End-to-end tests (Playwright)
│   │   ├── analyst-journey.spec.ts # Full user journey test
│   │   └── stub-api.ts            # Mock API for deterministic E2E tests
│   │
│   └── .storybook/                # Component explorer configuration
│
├── infra/                          # Infrastructure as code
│   └── docker-compose.yml          # TimescaleDB + Neo4j + Redis (local dev)
│
├── whalewisdom_data/               # Structured output from Bright Data scraper
│   ├── berkshire-hathaway-inc.json # Berkshire Hathaway holdings
│   ├── bridgewater-associates-inc.json
│   ├── d-e-shaw-co-inc.json
│   ├── fidelity-management-amp-research-co-ma.json
│   ├── franklin-resources-inc.json
│   ├── invesco-plc-london.json
│   ├── millennium-management-l-l-c.json
│   ├── northern-trust-corp.json
│   ├── point72-asset-management-lp.json
│   ├── price-t-rowe-associates-inc-md.json
│   └── state-street-corp.json
│
├── designs/                        # Dashboard screenshots
├── .github/workflows/ci.yml        # CI: lint, type-check, test, build, audit
├── .husky/                         # Git hooks (format, lint, type-check, emoji check)
└── package.json                    # Workspace root (npm workspaces)
```

---

## Tech Stack

| Layer                 | Technology                                  | Purpose                                                    |
| --------------------- | ------------------------------------------- | ---------------------------------------------------------- |
| **Scraping**          | Bright Data Scraper Studio                  | Custom AI scrapers with self-healing                       |
| **Backend**           | Python 3.11, FastAPI, Pydantic              | REST API, data pipeline, validation                        |
| **AI**                | Google Gemini                               | Page extraction, normalization, copilot, anomaly detection |
| **Time-series DB**    | TimescaleDB (PostgreSQL)                    | Price history, institutional holdings                      |
| **Graph DB**          | Neo4j                                       | Supply-chain relationships, ripple analysis                |
| **Cache/Rate Limit**  | Redis                                       | Per-IP rate limiting                                       |
| **Frontend**          | Next.js 15, React, TypeScript, Tailwind CSS | Interactive dashboard                                      |
| **AI Agent Protocol** | MCP (Model Context Protocol)                | IDE/agent integration                                      |
| **Testing**           | Pytest, Vitest, Playwright, Storybook       | Unit, component, E2E, visual                               |
| **Infrastructure**    | Docker Compose                              | Local database provisioning                                |
| **CI/CD**             | GitHub Actions                              | Automated quality gates                                    |

---

## Setup and Installation

### Prerequisites

- Node.js 22+ and npm 10+
- Python 3.11+
- Docker (or Podman) with Compose support
- Bright Data API key (required — for Scraper Studio scrapers)
- Google Gemini API key (required — for AI services)

### Quick Start

```bash
git clone <repository-url> shadow-cpi
cd shadow-cpi

# 1. Configuration
cp .env.example .env      # Fill in BRIGHTDATA_API_KEY and GEMINI_API_KEY

# 2. Start databases (TimescaleDB, Neo4j, Redis)
docker compose -f infra/docker-compose.yml up -d

# 3. Install frontend dependencies
npm install

# 4. Install backend dependencies
cd backend
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
cd ..

# 5. Create database schema and seed the supply-chain graph
backend/.venv/Scripts/python -m shadow_cpi.db.prepare

# 6. Collect data from all sources
backend/.venv/Scripts/python -m shadow_cpi.collect
```

### Environment Variables

| Variable                    | Required    | Purpose                                                                |
| --------------------------- | ----------- | ---------------------------------------------------------------------- |
| `BRIGHTDATA_API_KEY`        | Yes         | Authenticates Bright Data Scraper Studio API calls                     |
| `GEMINI_API_KEY`            | Yes         | Google Gemini for AI extraction, copilot, healing                      |
| `SCRAPER_STUDIO_COLLECTORS` | Yes         | Maps source IDs to collector IDs (e.g., `lme_copper_scraper=c_msw...`) |
| `EIA_API_KEY`               | Optional    | EIA petroleum spot prices (free)                                       |
| `USDA_MARS_API_KEY`         | Optional    | USDA grain prices (free)                                               |
| `SEC_EDGAR_USER_AGENT`      | Recommended | Contact email for SEC EDGAR compliance                                 |
| `CRON_SECRET`               | Optional    | Protects the admin heal endpoint                                       |

---

## Running the Application

```bash
# Dashboard on http://localhost:3000
npm run dev

# API on http://localhost:8000 (docs at /docs)
backend/.venv/Scripts/python -m shadow_cpi.api.main

# Collect from all sources now
backend/.venv/Scripts/python -m shadow_cpi.collect

# Run on schedule (respects each source's publish frequency)
backend/.venv/Scripts/python -m shadow_cpi.orchestration.scheduler

# MCP server for AI agents (stdio protocol)
backend/.venv/Scripts/python -m shadow_cpi.mcp_server.main
```

---

## Data Sources

| Source                    | Type               | Frequency | What It Collects               |
| ------------------------- | ------------------ | --------- | ------------------------------ |
| `lme_copper_scraper`      | Bright Data Studio | Daily     | Copper futures price           |
| `fbx_scraper`             | Bright Data Studio | Daily     | Container freight (12 lanes)   |
| `baltic_dry_scraper`      | Bright Data Studio | Daily     | Baltic Dry Index               |
| `oilprice_scraper`        | Bright Data Studio | Daily     | Oil benchmarks                 |
| `gold_scraper`            | Bright Data Studio | Daily     | Gold spot price                |
| `aluminum_scraper`        | Bright Data Studio | Daily     | Aluminum price                 |
| `natural_gas_scraper`     | Bright Data Studio | Daily     | Henry Hub natural gas          |
| `wheat_scraper`           | Bright Data Studio | Daily     | CBOT wheat futures             |
| `corn_scraper`            | Bright Data Studio | Daily     | CBOT corn futures              |
| `soybeans_scraper`        | Bright Data Studio | Daily     | CBOT soybean futures           |
| `steel_scraper`           | Bright Data Studio | Daily     | US HRC steel                   |
| `whalewisdom_13f_scraper` | Bright Data Studio | Quarterly | Fund holdings enrichment       |
| `eia_wti_page`            | Direct (no auth)   | Daily     | WTI crude from EIA.gov         |
| `eia_brent_page`          | Direct (no auth)   | Daily     | Brent crude from EIA.gov       |
| `eia_petroleum_spot`      | Official API       | Daily     | EIA petroleum prices           |
| `usda_grain_prices`       | Official API       | Weekly    | USDA crop prices               |
| `sec_edgar_13f`           | Official API       | Quarterly | SEC 13F institutional holdings |

---

## API Endpoints

| Endpoint                                  | Method    | Purpose                                  |
| ----------------------------------------- | --------- | ---------------------------------------- |
| `/health`                                 | GET       | Liveness check, version info             |
| `/api/risk-map`                           | GET       | Latest price for every tracked commodity |
| `/api/commodities/{name}/trend?days=30`   | GET       | Price history for one entity             |
| `/api/graph/ripple/{commodity}?depth=2`   | GET       | Supply-chain impact graph                |
| `/api/institutional/overview`             | GET       | All funds, top stocks, moves             |
| `/api/institutional/holders/{ticker}`     | GET       | Who holds a given stock                  |
| `/api/institutional/filer/{cik}/holdings` | GET       | One fund's portfolio                     |
| `/api/pipeline-health`                    | GET       | Collector run history                    |
| `/api/pipeline-health/stream`             | GET (SSE) | Live pipeline events                     |
| `/api/copilot/ask`                        | POST      | AI Q&A with data citations               |
| `/api/admin/scrapers/{id}/heal`           | POST      | Trigger self-healing for a scraper       |

---

## MCP Server (AI Agent Interface)

The MCP server lets AI agents and IDEs query Shadow CPI directly:

```json
{
  "mcpServers": {
    "shadow-cpi": {
      "command": "python",
      "args": ["-m", "shadow_cpi.mcp_server.main"]
    }
  }
}
```

**Available tools:**

| Tool                          | Description                                  |
| ----------------------------- | -------------------------------------------- |
| `get_commodity_price_trend`   | Price history for any tracked commodity      |
| `analyze_supply_chain_impact` | What a price move affects downstream         |
| `get_institutional_holders`   | Which funds hold a given stock               |
| `check_data_freshness`        | When each source last collected successfully |
| `ask_shadow_cpi_copilot`      | Free-form question answered from stored data |

---

## Testing

```bash
# Backend (35+ test files, >80% coverage enforced)
cd backend
.venv/Scripts/python -m pytest
.venv/Scripts/python -m pytest --cov --cov-report=term-missing

# Frontend (component + unit tests)
npm run test
npm run test:coverage

# End-to-end (Playwright, no real DB needed)
npm run test:e2e

# Component explorer
npm run storybook
```

Both suites fail if coverage drops below 80%. The E2E test uses a stub API with fixed responses — no databases or API keys needed.

---

## AI Disclosure

AI coding assistants (Kiro CLI / Claude) were used during development for:

- Code generation and refactoring
- Test writing
- Documentation drafting

All generated code was reviewed, understood, and verified by the team. The architecture decisions, scraper designs, database schema, and product logic represent original work completed during the hackathon period.
