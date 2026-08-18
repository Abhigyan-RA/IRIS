# Shadow CPI — Alternative Data Intelligence Platform

### Product Requirements Document \+ End-to-End Architecture ("the bible")

Version 1.0 — prepared for hackathon build-out • Last verified against live sources on **15 Aug 2026**

> **How to use this file:** This is the only document you need. Feed it whole into your coding agent (Claude Code, Cursor, etc.) as project context. Part 1 is *what* to build and *why*. Part 2 is *how* to build it — precise enough that an agent can scaffold the repo without asking you follow-up questions. Section 20 tells the agent what order to build things in.

---

## Table of Contents

**Part 1 — Product**

1. [Executive Summary](#1-executive-summary)  
2. [Verification & Correction Notes — read this first](#2-verification--correction-notes--read-this-first)  
3. [The Problem](#3-the-problem)  
4. [Who This Is For](#4-who-this-is-for)  
5. [Plain-English Data Glossary](#5-plain-english-data-glossary)  
6. [What the User Actually Sees](#6-what-the-user-actually-sees)  
7. [User Flow](#7-user-flow)  
8. [Verified Data Sources](#8-verified-data-sources)  
9. [Non-Functional Requirements](#9-non-functional-requirements)  
10. [Legal, ToS & Compliance Notes](#10-legal-tos--compliance-notes)  
11. [Risks & Mitigations](#11-risks--mitigations)  
12. [Hackathon Roadmap & Demo Script](#12-hackathon-roadmap--demo-script)

**Part 2 — Architecture** 13\. [Tech Stack at a Glance](#13-tech-stack-at-a-glance) 14\. [High-Level Architecture (HLD)](#14-high-level-architecture-hld) 15\. [Where Gemini Fits In](#15-where-gemini-fits-in) 16\. [Low-Level Design (LLD)](#16-low-level-design-lld) 17\. [Deep-Dive: The WhaleWisdom Example](#17-deep-dive-the-whalewisdom-example) 18\. [Appendix — Sample Payloads](#18-appendix--sample-payloads)

---

# PART 1 — PRODUCT

## 1\. Executive Summary

Government inflation data (CPI) is published monthly and describes prices from weeks ago. **Shadow CPI** is a platform that watches the raw, real-world prices — freight rates, commodity spot prices, bulk crop prices, and what hedge funds are actually buying — every day instead of every month, and shows a non-technical user what's about to get more expensive and why.

It does this by scraping public data from \~10 verified sources, some via official free APIs and some via **Bright Data Scraper Studio** (which bypasses anti-bot protection and *self-heals* when a site changes its layout), storing the result in a time-series database (price history) and a graph database (supply-chain relationships), and serving it through a **Next.js dashboard** for humans and an **MCP server** for AI coding agents. **Gemini** is the reasoning layer that turns messy scraped text into clean data, explains *why* a price spike matters, and answers free-form questions.

The single most impressive thing this project can show a judge is not the dashboard — it's that when a target website changes its HTML overnight, **the pipeline notices, repairs itself, and keeps going with zero human intervention.** Everything below is built around making that moment demonstrable.

---

## 2\. Verification & Correction Notes — read this first

You asked me to verify every website and make no mistakes. I searched and fetched live sources for everything below. Here is exactly what I changed from your draft and why — so nothing is silently different from what you expected.

| \# | Your draft said | What I verified | What I changed |
| :---- | :---- | :---- | :---- |
| 1 | `Gemini 3.0 Flash` | As of 14 Aug 2026, Google's live model catalog (`ai.google.dev/gemini-api/docs/models`) no longer lists a `gemini-3.0-flash` — the current stable lineup is **Gemini 3.7 Flash** (latest, GA), 3.6, 3.5, with 2.0 Flash already shut down. | The `.env` uses `GEMINI_MODEL=gemini-flash-latest`, a Google-maintained alias that always resolves to the current recommended Flash model, so your app never silently breaks when Google ships 3.8. You can pin `gemini-3.7-flash` explicitly if you want reproducibility instead of auto-upgrades. Just drop in your key — nothing else to do. |
| 2 | MCP server code used `server.tool(...)` | Anthropic's own current MCP-builder reference explicitly says **do not** use `server.tool()` — it's deprecated in favor of `server.registerTool()` with a `structuredContent` return. A newer `@modelcontextprotocol/server` v2 package also exists but is beta as of the 2026-07-28 spec (weeks old). | LLD uses `@modelcontextprotocol/sdk` (the stable, 65k+ project, v1.x line) with `registerTool()` — current best practice without betting a hackathon deadline on a brand-new major version. |
| 3 | WhaleWisdom scraping was framed as *the* solution for 13F data | WhaleWisdom itself just re-parses **SEC EDGAR** 13F filings within minutes of posting (confirmed on WhaleWisdom's own FAQ). SEC EDGAR publishes the same underlying data as free, structured, zero-anti-bot, official government JSON/XML. | Architecture now uses **two paths**: SEC EDGAR direct as the *production-grade primary source* (§17), and Bright Data self-healing on WhaleWisdom's UI as the *demo path* that actually satisfies the hackathon's "prove resilience" judging criterion. You get both a robust app **and** the impressive demo. |
| 4 | Baltic Exchange listed as a direct scrape target | `balticexchange.com`'s real index numbers sit behind a paid membership; the page only shows methodology. | Swapped in `tradingeconomics.com/commodity/baltic-dry`, which mirrors the publicly-reported BDI number and is scrape-friendly. |
| 5 | `markets.businessinsider.com/commodities/copper-price` | Unstable / inconsistent under Business Insider's ongoing rebrand. | Replaced with `investing.com/commodities/copper` and `tradingeconomics.com/commodities`, both confirmed live today. |
| 6 | Bright Data pseudo-code endpoint `/dca/collectors/{id}/refactor_template` | This is a **real, currently-documented endpoint** — I found it independently in Bright Data's official CLI source and docs. Your draft was right. | Kept, and I added the two endpoints around it that make the loop actually work end-to-end: `POST /dca/trigger_immediate` (run the scraper) and `POST /resume_automation_job` (auto-approve the AI's fix so it's a *fully* hands-off loop, not one that waits for a human to click approve). |
| 7 | Freightos treated as scrape-only | Freightos actually has a **free, no-API-key public endpoint**: `ship.freightos.com/api/shippingCalculator`. | Added as the preferred integration; scraping `data.freightos.com` is now the fallback for the full FBX index display. |

Everything else below (EIA, USDA, FAO, Xeneta, SEC EDGAR, TimescaleDB, Neo4j) checked out and is cited with the live URL I actually fetched or searched.

---

## 3\. The Problem

**In technical language:** Official inflation indices (CPI, PPI) are lagging, monthly, backward-looking aggregates. By the time they publish, institutional decisions have already been made on stale information. Ground-truth, high-frequency price signals exist publicly on the web but are fragmented across dozens of differently-structured, frequently-changing, sometimes bot-protected sites, making them expensive to track reliably.

**In plain English:** Imagine trying to predict tomorrow's weather using last month's newspaper. That's what a supply chain manager does when they only have the government's CPI report. Meanwhile, the actual price of shipping a container from Shanghai, or a ton of copper, or a bushel of wheat, changes *today* — publicly, on websites — and it moves *before* those changes show up in a headline inflation number. The problem is nobody can watch 15 different messy websites by hand every day, and even if they wrote a script to do it, the sites redesign themselves and break the script within weeks.

This platform is that script — except it fixes itself.

---

## 4\. Who This Is For

| Persona | What they need | What they get |
| :---- | :---- | :---- |
| **Supply Chain / Procurement Director** | To know *today* if a raw material or freight lane is about to get more expensive, so they can lock in a contract before the price moves further. | The Global Risk Map \+ Ripple Effect Graph: "steel is up 8% this week, and here's every industry that depends on it." |
| **Quantitative Analyst / Hedge Fund Researcher** | A fast read on where prices are heading and what other institutional investors are doing about it — "Shadow CPI" plus "smart money" positioning. | Commodity trend charts \+ the Institutional Sentiment panel powered by 13F data. |
| **AI / Software Developer** | To pull this data programmatically into their own agent or app without writing scrapers themselves. | The MCP server — add it to Claude Code, Cursor, or any MCP-compatible IDE and query it in plain English. |
| **Hackathon Judge** | Proof that the system is technically real, not a static demo, and that it's resilient to the exact failure mode (site redesigns) that kills most scraping projects. | The Pipeline Health / Self-Healing Audit Log tab, purpose-built to be shown live. |

---

## 5\. Plain-English Data Glossary

This is the "so what does this number actually mean" section — use it as on-hover tooltip copy in the UI.

**Shadow CPI / Alternative Data** — Official inflation numbers come out once a month, weeks late. "Alternative data" means watching the *real* prices — a shipping container, a ton of copper — every day instead, as an early, unofficial preview of where official inflation is heading.

**Freight rate index (FBX, XSI) — and how it tells you a shipment is running late.** When a company books a shipping container, the price is set by supply and demand for ship space, exactly like a plane ticket. The Freightos Baltic Index (FBX) and Xeneta Shipping Index (XSI) track the average price of a 40-foot container on \~12 major ocean routes, updated daily. We don't get any single package's tracking status — carriers keep that private — but we get two public early-warning signals that stand in for it:

- **Price spikes** on a lane usually mean demand is outrunning ship capacity, which is the classic precursor to backlogs. Rates on Shanghai→LA spiked for weeks *before* the 2021 port-congestion crisis became visible in delivery times.  
- **Rate volatility \+ port dwell time** (published alongside some indices) — if ships are waiting longer before they can unload, on-time delivery odds drop across the whole lane, not just for one shipment. We turn this into a plain "Delay Risk" badge per trade lane: rate trend \+ volatility, not a single package's status.

**Commodity spot price (e.g., LME copper)** — The price to buy the physical commodity *right now*, as opposed to a futures contract for later delivery. Copper is nicknamed "Dr. Copper" because it's in almost everything electrical (wiring, EV batteries, motors) — its price is a real-time pulse check on global industrial activity. Rising copper usually means either supply is constrained (mine strikes, smelter outages) or demand is booming (EV/construction) — both eventually show up in consumer prices.

**13F filing / "whale watching"** — Any US investment manager overseeing more than $100M must publicly disclose its stock holdings to the SEC every quarter, on a form called 13F. This is 100% public — not insider information — it's just filed as dense XML that's hard to read at scale. Sites (and our platform) parse it the moment it's posted and show, in plain English, what changed: *"Bridgewater increased its Nvidia position 14% this quarter."*

**Bulk agricultural / fertilizer prices** — Wheat, corn, soy, and fertilizer costs feed directly into food-manufacturing and animal-feed costs. A spike today shows up on grocery shelves months later — tracking it early gives procurement teams lead time.

**Self-healing scraper** — A normal scraper looks for data in a fixed spot on a page (e.g., "the price is always in the 3rd `<td>` of this table"). When a site redesigns its page, that spot moves, and the scraper silently returns nothing. A *self-healing* scraper is told in plain English *what* to look for ("the current price"), not *where* — so when the layout changes, an AI re-reads the new page, finds where "current price" moved to, and fixes the extraction automatically.

---

## 6\. What the User Actually Sees

Five screens, in the order a user actually uses them:

| Screen | What it shows | Why it exists |
| :---- | :---- | :---- |
| **Global Risk Map** | A world map that flashes red over regions with a live cost spike — e.g. "Steel prices up 8% in the US Midwest." Default landing view. | Zero-effort entry point: shows *where something changed* before the user asks anything. |
| **Ripple Effect Graph** | Click any commodity (e.g. Copper) and a graph fans out showing what it feeds into — Copper → Stator Coils → EV Battery Manufacturing → Consumer Electronics. | Answers "why should I care" — a price move is meaningless without knowing what it touches downstream. |
| **Institutional Sentiment** | "What did the smart money do this quarter" — hedge fund 13F holdings and quarter-over-quarter deltas for stocks connected to whatever commodity/industry the user is looking at. This is the WhaleWisdom-powered layer. | Cross-checks the raw commodity data against how professional investors are actually positioning — a second, independent signal. |
| **Pipeline Health / Self-Healing Audit Log** | A live feed: `⚠️ 03:00 WhaleWisdom layout changed → 🤖 03:02 Bright Data self-healed it → ✅ 03:03 data flowing again, zero downtime.` | This is the judge-facing screen. It's the proof the system is real infrastructure, not a static scrape-once demo. |
| **Ask the Data (AI Copilot)** | A chat box. The user types "should I lock in a steel contract this month?" and Gemini answers in plain English, citing the specific price trend, graph relationship, and hedge fund positioning it used. | Lets a non-technical user skip navigating the other four screens entirely. |

---

## 7\. User Flow

flowchart TD

    A\["Analyst logs in"\] \--\> B\["Global Risk Map:\<br/\>heat map of live cost spikes"\]

    B \--\> C{"Clicks a flashing region,\<br/\>e.g. US Midwest steel"}

    C \--\> D\["Drill-down panel:\<br/\>price, percent change, trend chart, source link"\]

    D \--\> E\["Clicks Show Ripple Effect"\]

    E \--\> F\["Ripple Effect Graph:\<br/\>Steel to Construction to Auto industries"\]

    F \--\> G\["Switches to Institutional Sentiment tab"\]

    G \--\> H\["Sees which hedge funds bought\<br/\>steel-exposed stocks this quarter"\]

    H \--\> I\["Asks the AI Copilot a question"\]

    I \--\> J\["Gemini synthesizes price plus graph plus sentiment\<br/\>into one cited, plain-English answer"\]

    D \--\> K\["Pipeline Health tab"\]

    K \--\> L\["Self-Healing Audit Log proves\<br/\>the system survives real-world breakage"\]

---

## 8\. Verified Data Sources

Every URL below was searched and, where noted, fetched live on 15 Aug 2026\. "Access method" tells your ingestion service which path to take — **official free APIs are always preferred over scraping** because they're faster, don't break, and carry zero ToS risk. Scraping (via Bright Data) is reserved for sites that genuinely have no public API — which, not coincidentally, is also where the "self-healing" story is real rather than decorative.

### 8.1 Freight & Shipping

| Source | URL | What you get | Access method | Cadence |
| :---- | :---- | :---- | :---- | :---- |
| Freightos public Shipping Calculator | `https://ship.freightos.com/api/shippingCalculator` | Point-to-point ocean/air freight price estimates. GET with URL query params, **no API key required**, free marketplace data (attribution required). | **Official public API** | Real-time |
| Freightos Baltic Index (FBX) dashboard | `https://data.freightos.com/` | Global FBX index \+ all 12 tradelane sub-indices (e.g. FBX01 China/East Asia→N. America West Coast), each with day-over-day % change. | Bright Data scrape (JS-rendered charts) | Daily, published \~14:00 UTC |
| Freightos Developer Portal | `https://developer.freightos.com/apis` | Documented beta "FBX Global Container Index API" \+ Duties/HS-code API — free registration. | Official API (beta, registration) | Daily |
| Xeneta Shipping Index (XSI), public | `https://xsi.xeneta.com/` | Global \+ regional (Far East, Europe, US) import/export container rate sub-indices, 12 tradelanes. | Bright Data scrape | Daily, \~2-day reporting lag |
| Baltic Dry Index (public mirror) | `https://tradingeconomics.com/commodity/baltic-dry` | Composite dry-bulk shipping cost index (Capesize/Panamax/Supramax). The official `balticexchange.com` numbers require a paid membership — this mirrors the publicly reported value. | Bright Data scrape | Daily |

### 8.2 Energy & Raw Materials

| Source | URL | What you get | Access method | Cadence |
| :---- | :---- | :---- | :---- | :---- |
| EIA Open Data API | `https://api.eia.gov/v2/petroleum/pri/spt/data` (free key at `eia.gov/opendata`) | WTI (Cushing) and Brent (Europe) crude spot prices, gasoline, heating oil, propane — official U.S. government JSON. | **Official public API** | Daily/weekly by series |
| EIA petroleum data (human page) | `https://www.eia.gov/petroleum/data.php` | Same data, browsable. | Reference only | — |
| Copper / industrial metals | `https://www.investing.com/commodities/copper` and `https://www.investing.com/indices/lme-daily` | Live COMEX copper futures (USD/lb) and the LME metals index. | Bright Data scrape | Real-time (delayed) |
| Multi-commodity single page | `https://tradingeconomics.com/commodities` | One page covering energy, metals, *and* agriculture — efficient single scrape target for a fallback/cross-check layer. | Bright Data scrape | Daily |
| Global crude benchmarks | `https://oilprice.com/oil-price-charts/` | 150+ global crude blends and benchmark indexes. **Note:** OilPrice.com's terms explicitly prohibit redistributing the live feed/tables without consent — fine for an internal dashboard, not for reselling the raw data. | Bright Data scrape | Real-time |

### 8.3 Agriculture & Food

| Source | URL | What you get | Access method | Cadence |
| :---- | :---- | :---- | :---- | :---- |
| USDA AMS MyMarketNews (MARS) API | `https://marsapi.ams.usda.gov/services/v1.2/reports` (free key at `mymarketnews.ams.usda.gov/mymarketnews-api`) | Bulk crop pricing (wheat, corn, soy), livestock, specialty crops — official USDA JSON. | **Official public API** | Daily |
| FAO GIEWS FPMA Tool | `https://fpma.apps.fao.org/giews/food-prices/tool/public/` (also mirrored at `fpma.fao.org`) | Domestic & international food price series across 88+ countries, plus a built-in "price anomaly" early-warning indicator. | Bright Data scrape (Angular app, no full public API) | Weekly/monthly |
| FAO FPMA news/alerts | `https://www.fao.org/giews/food-prices/home/en/` | Narrative alerts on countries with abnormal food prices. | Bright Data scrape | As published |

### 8.4 Institutional Sentiment (Hedge Fund 13F Holdings)

| Source | URL | What you get | Access method | Cadence |
| :---- | :---- | :---- | :---- | :---- |
| **SEC EDGAR — Form 13F bulk data sets** | `https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets` | Every 13F filing, flattened to CSV/XML, straight from the primary regulator. Zero anti-bot, zero cost, zero legal ambiguity. | **Official bulk download — production primary source** | Quarterly |
| SEC EDGAR — per-filer submissions | `https://data.sec.gov/submissions/CIK##########.json` (10-digit, zero-padded CIK) | Real-time filing index per manager, the moment SEC posts it. Requires a descriptive `User-Agent` header (SEC policy). | **Official API** | Real-time |
| SEC EDGAR company search | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany` | Look up a manager's CIK by name. | Official | — |
| **WhaleWisdom filer pages** (the hackathon demo target) | `https://whalewisdom.com/filer/bridgewater-associates-lp` | Pre-parsed, human-readable holdings table with quarter-over-quarter deltas and a proprietary "WhaleScore." Protected by anti-bot \+ a UI that changes periodically. | Bright Data Scraper Studio (self-healing) — **demo path** | Real-time (WhaleWisdom itself polls SEC hourly) |
| WhaleWisdom's own commercial API | `https://whalewisdom.com/shell/api_help` | Documented `filer_lookup`, `holdings_comparison`, `holders` commands — a real, official API, gated behind a paid subscription. | Official API (paid) | — |

> See §17 for exactly how the SEC EDGAR path and the WhaleWisdom scrape path fit together — you want both, for different reasons.

---

## 9\. Non-Functional Requirements

| Category | Requirement |
| :---- | :---- |
| **Data freshness** | Freight/energy: ≤6h stale. Agriculture: ≤24h. Institutional (13F): same-day as SEC posting. |
| **Self-healing SLA** | From DOM-drift detection to data flowing again: \<15 minutes unattended (matches Bright Data's documented refactor turnaround). |
| **Availability** | Dashboard 99% during demo window; ingestion failures on one source must never block others (isolate per-collector). |
| **Security** | All API keys server-side only, never shipped to the browser. SEC EDGAR calls must set a real, descriptive `User-Agent` per SEC's fair-access policy. |
| **Cost control** | Cap Gemini calls per day (env-configurable); cap Bright Data collector runs per day; alert (not silently fail) on quota exhaustion. |
| **Auditability** | Every price row stores its `source_url` and `ingestion_method` — no unattributed numbers on the dashboard. |

---

## 10\. Legal, ToS & Compliance Notes

Kept brief and practical, not legal advice:

- **Government sources (EIA, USDA, SEC, FAO) are explicitly public-domain / free-to-use.** Zero risk here — use these as your backbone wherever they overlap with a commercial site.  
- **Commercial aggregators (WhaleWisdom, investing.com, OilPrice.com, Xeneta)** generally have Terms of Service that restrict automated access and/or redistribution of their data. Scraping their *public, unauthenticated* pages for internal analysis (not resale of the raw feed) is common practice in the alternative-data industry and is exactly the scenario Bright Data's Web Unlocker is built for — but it is a ToS gray area, not a guaranteed-safe one. Fine for a hackathon demo; if this became a commercial product, budget time to review each site's ToS or switch to their official paid API (WhaleWisdom has one — see §8.4).  
- **OilPrice.com** explicitly states its live data/tables may not be redistributed without written consent — use internally, cite the source, don't re-publish the raw feed.

---

## 11\. Risks & Mitigations

| Risk | Mitigation |
| :---- | :---- |
| Target site escalates anti-bot beyond what Web Unlocker handles | Fall back to the official API where one exists (EIA/USDA/SEC already cover 3 of 4 verticals); degrade gracefully with "last known price" \+ staleness badge. |
| Self-heal produces a wrong mapping (false positive) | Keep human-in-the-loop approval (`resume_automation_job`) as the default in production; only auto-approve (`auto_save: true`) for the hackathon demo where speed matters more. |
| Gemini hallucinates in the Copilot answer | Always ground the Copilot in retrieved DB/graph rows (RAG-style) and require it to cite the specific row/source it used; never let it answer from parametric memory alone. |
| Rate limits / cost overrun on Bright Data or Gemini | Env-configurable daily caps \+ cron backoff; batch normalization calls instead of one Gemini call per row. |
| Scraped-data ToS exposure | See §10 — isolate which sources are "safe to scale" (official APIs) vs. "demo-only" (scraped commercial sites). |

---

## 12\. Hackathon Roadmap & Demo Script

**Day 0 (setup, \~2h):** Provision TimescaleDB \+ Neo4j (Docker Compose, §16.1), register free EIA/USDA keys, get Bright Data \+ Gemini keys, scaffold repo.

**Day 1 (ingestion \+ storage):** Build the 3 official-API ingestors (EIA, USDA, SEC EDGAR) first — they're the fastest wins and need no anti-bot handling. Then build 2–3 Bright Data collectors (start with `investing.com/commodities/copper` — simple table, good for proving the pattern). Get rows landing in TimescaleDB.

**Day 1.5 (self-healing \+ graph):** Seed the Neo4j supply-chain graph (§16.4). Build the health-check watchdog and wire it to the Bright Data `refactor_template` endpoint. **Pre-record or script the "break it live" demo now** (§17) — this is your highest-value judge moment and needs a rehearsed, reliable trigger, not a live unpredictable break.

**Day 2 (serving \+ UI \+ AI):** REST API \+ MCP server (§16.5, §16.8). Next.js dashboard: Risk Map → Ripple Graph → Institutional panel → Pipeline Health → Copilot, in that build order (matches the user flow, so a partially-finished build still demos top-to-bottom). Wire Gemini into normalization \+ Copilot last, once real data is flowing.

**Demo script (map directly to judging criteria):**

1. **Technical excellence:** Load the live dashboard, click through Risk Map → Ripple Graph → Institutional Sentiment — real data, real sources, cited.  
2. **Potential impact:** 30 seconds on the "weather report vs. newspaper" framing from §3 — why this beats waiting for CPI.  
3. **Reliability / self-healing (the finale):** Open Pipeline Health. Trigger the pre-staged "simulate the break" script against WhaleWisdom (§17.3) live. Watch the log go `⚠️ → 🤖 → ✅` in front of the judges. Ask the Copilot a question that depends on the just-healed data, proving the pipeline didn't just recover — it recovered *usefully*.

---

# PART 2 — ARCHITECTURE

## 13\. Tech Stack at a Glance

| Layer | Choice | Why |
| :---- | :---- | :---- |
| Ingestion (scrape) | Bright Data Scraper Studio \+ CLI | Natural-language extraction, built-in Web Unlocker (anti-bot bypass), documented self-healing API. |
| Ingestion (official APIs) | Native fetch to EIA / USDA MARS / SEC EDGAR | Free, stable, zero anti-bot — always preferred where available. |
| Processing | Fastapi | One language across ingestion, API, and MCP server. |
| AI reasoning | Gemini (`gemini-flash-latest`, currently resolves to **Gemini 3.7 Flash**) via `generateContent` REST endpoint | Fast, cheap, stable, fully-supported endpoint — no need for the newer stateful Interactions API for these one-shot use cases. |
| Time-series store | TimescaleDB (Postgres extension; Tiger Data's Docker image `timescale/timescaledb:latest-pg16`) | SQL you already know, hypertables built for exactly this "price over time" shape. |
| Graph store | Neo4j (AuraDB Free tier is sufficient for a hackathon) | Native traversal for "what does this commodity feed into." |
| Serving | REST API (Fastify/Express) \+ MCP server (`@modelcontextprotocol/sdk`) | REST for the dashboard, MCP for AI agents/IDEs. |
| Frontend | Next.js 15+ (App Router), Recharts, a force-graph library for the Ripple view | Fast to ship, huge ecosystem for charts/maps. |
| Orchestration | APScheduler  | Scheduled scrape jobs \+ the self-heal watchdog. |

---

## 14\. High-Level Architecture (HLD)

flowchart LR

    subgraph Sources\["Public Data Sources"\]

        S1\["EIA Open Data API"\]

        S2\["USDA MARS API"\]

        S3\["SEC EDGAR"\]

        S4\["Freightos and Xeneta"\]

        S5\["WhaleWisdom, investing.com,\<br/\>oilprice.com, FAO FPMA"\]

    end

    subgraph Ingestion\["Ingestion Layer"\]

        I1\["Official API Clients\<br/\>EIA, USDA, SEC"\]

        I2\["Bright Data Scraper Studio\<br/\>Web Unlocker plus Self-Healing"\]

    end

    subgraph Processing\["Processing and AI Layer"\]

        P1\["Normalizer Service\<br/\>fastapi"\]

        P2\["Gemini 3.7 Flash\<br/\>normalization, narration, copilot"\]

    end

    subgraph Storage\["Storage Layer"\]

        D1\[("TimescaleDB\<br/\>price and holdings time-series")\]

        D2\[("Neo4j\<br/\>supply chain and institutional graph")\]

    end

    subgraph Serving\["Serving Layer"\]

        M1\["REST API"\]

        M2\["MCP Server"\]

    end

    subgraph Presentation\["Presentation Layer"\]

        U1\["Next.js Dashboard"\]

        U2\["IDEs and AI Agents via MCP"\]

    end

    S1 \--\> I1

    S2 \--\> I1

    S3 \--\> I1

    S4 \--\> I2

    S5 \--\> I2

    I1 \--\> P1

    I2 \--\> P1

    P1 \<--\> P2

    P1 \--\> D1

    P1 \--\> D2

    D1 \--\> M1

    D2 \--\> M1

    D1 \--\> M2

    D2 \--\> M2

    M1 \--\> U1

    M2 \--\> U2

**Layer-by-layer, in plain English:**

1. **Ingestion** — two parallel paths. Boring-but-reliable official APIs for the sources that have them; Bright Data for the sources that don't.  
2. **Processing & AI** — every payload, regardless of source, passes through one Normalizer service that validates it and calls Gemini to turn anything messy (scraped prose, inconsistent field names) into one strict schema.  
3. **Storage** — TimescaleDB for "what was the price of X at time T" questions; Neo4j for "what does X affect" questions. They're kept in sync by the same Normalizer write.  
4. **Serving** — the same underlying data is exposed twice: as a REST API for the web dashboard, and as MCP tools for AI agents. Neither layer talks to the databases directly except through this serving layer.  
5. **Presentation** — humans get the Next.js dashboard; AI agents (Claude Code, Cursor, etc.) get the MCP server.

---

## 15\. Where Gemini Fits In

Six concrete, explicit uses — not a vague "AI-powered" claim:

| \# | Use case | Where it runs | Input | Output |
| :---- | :---- | :---- | :---- | :---- |
| 1 | **Unstructured → structured normalization** | Right after every scrape, in the Normalizer | Raw scraped text/JSON (e.g. FAO bulletin prose, an FBX chart's inconsistent labels) | Strict JSON matching the `commodity_prices` schema — nothing else, no prose |
| 2 | **Self-heal prompt drafting** | Watchdog, when a health check fails | The list of null/missing fields \+ a snippet of the new HTML | A precise one-sentence repair instruction, sent straight into Bright Data's `refactor_template` |
| 3 | **Ripple-effect explanation** | Ripple Graph API, on click | The Neo4j traversal result (nodes \+ edge weights) | A 1–2 sentence plain-English "why this matters" caption |
| 4 | **Audit log narration** | Pipeline Health event stream | A raw event row (`scraper_id`, `event_type`, timestamp) | The judge-facing `⚠️ → 🤖 → ✅` narrative line |
| 5 | **Ask-the-Data Copilot** | `/api/copilot/ask` and the MCP tool `ask_shadow_cpi_copilot` | User's question \+ retrieved DB rows \+ graph context (RAG — never answered from memory alone) | A cited, plain-English answer |
| 6 | **Anomaly flagging** | Nightly batch job | 30-day price series per tracked entity | A flag \+ one-line explanation for statistically unusual moves |

All six use the same client wrapper (`packages/ai/gemini.ts`) hitting:

POST https://generativelanguage.googleapis.com/v1beta/models/{GEMINI\_MODEL}:generateContent

Header: x-goog-api-key: $GEMINI\_API\_KEY

This is Google's original, simple, one-shot `generateContent` endpoint. Google also now offers a newer, stateful "Interactions API" (GA since June 2026\) aimed at multi-turn agents — not needed here since every one of the six use cases above is a single, independent call with no session state to carry forward. Using the simpler endpoint means fewer moving parts for a time-boxed build.

---

## 16\. Low-Level Design (LLD)

### 16.1 Repo Structure

shadow-cpi/

├── apps/

│   ├── web/                  \# Next.js dashboard (App Router)

│   ├── api/                  \# REST API (Fastify) — orchestrates ingestion \+ serves data

│   └── mcp-server/           \# MCP server exposing tools to AI agents/IDEs

├── packages/

│   ├── ingestion/

│   │   ├── official/         \# eia.ts, usdaMars.ts, secEdgar.ts

│   │   └── brightdata/       \# collectors.ts, selfHeal.ts, client.ts

│   ├── db/

│   │   ├── timescale/        \# migrations \+ query helpers

│   │   └── neo4j/            \# cypher queries \+ seed graph

│   ├── ai/

│   │   ├── gemini.ts         \# thin client wrapper

│   │   └── prompts/          \# one file per use case in §15

│   └── shared/                \# zod schemas, shared TS types

├── infra/

│   └── docker-compose.yml    \# timescaledb, neo4j, redis

├── .env.example

└── SHADOW\_CPI\_PRD\_AND\_ARCHITECTURE.md   \# this file

### 16.2 Environment Variables

\# ── AI ─────────────────────────────────────────────

GEMINI\_API\_KEY=

GEMINI\_MODEL=gemini-flash-latest          \# pin gemini-3.7-flash instead for reproducible output

\# ── Bright Data ────────────────────────────────────

BRIGHTDATA\_API\_KEY=

BRIGHTDATA\_AUTO\_APPROVE\_HEAL=true         \# true for hackathon demo; false \= human-in-the-loop for prod

\# ── Databases ──────────────────────────────────────

DATABASE\_URL=postgresql://user:pass@localhost:5432/shadowcpi

NEO4J\_URI=neo4j+s://xxxx.databases.neo4j.io

NEO4J\_USER=neo4j

NEO4J\_PASSWORD=

\# ── Official free data-source keys (OPTIONAL but strongly recommended) ──

\# These replace fragile scraping with official, free, structured APIs

\# for 3 of the 4 verticals. The app still works without them — those

\# 3 sources just fall back to Bright Data scraping instead.

EIA\_API\_KEY=                              \# free at https://www.eia.gov/opendata

USDA\_MARS\_API\_KEY=                        \# free at https://mymarketnews.ams.usda.gov/mymarketnews-api

SEC\_EDGAR\_USER\_AGENT="ShadowCPI/1.0 (you@example.com)"   \# SEC requires a real contact string, not a key

\# ── App ─────────────────────────────────────────────

NEXT\_PUBLIC\_APP\_URL=http://localhost:3000

CRON\_SECRET=

> **Minimum to run anything:** `BRIGHTDATA_API_KEY` \+ `GEMINI_API_KEY`, exactly as you planned. Everything else above is free, optional, and only makes the app more robust — the three EIA/USDA/SEC keys take under 5 minutes total to get and remove the anti-bot problem entirely for those three verticals.

### 16.3 TimescaleDB Schema

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE commodity\_prices (

    id                UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

    entity\_name       VARCHAR(255) NOT NULL,       \-- e.g. "Steel\_HRC\_US", "Copper", "FBX01"

    sector            VARCHAR(50)  NOT NULL,       \-- freight | energy | metals | agriculture

    price             DECIMAL(14,4) NOT NULL,

    currency          VARCHAR(3)   NOT NULL,

    unit              VARCHAR(50)  NOT NULL,        \-- metric\_ton | barrel | feu | index\_point

    pct\_change\_1d     DECIMAL(6,3),

    pct\_change\_7d     DECIMAL(6,3),

    recorded\_at       TIMESTAMPTZ NOT NULL,

    source\_name       VARCHAR(100) NOT NULL,

    source\_url        TEXT NOT NULL,

    ingestion\_method  VARCHAR(20) NOT NULL,         \-- official\_api | brightdata\_scrape

    CONSTRAINT unique\_daily\_price UNIQUE (entity\_name, recorded\_at)

);

SELECT create\_hypertable('commodity\_prices', 'recorded\_at');

CREATE TABLE institutional\_holdings (

    id                 UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

    filer\_name         VARCHAR(255) NOT NULL,       \-- e.g. "Bridgewater Associates"

    filer\_cik          VARCHAR(20),                  \-- e.g. "0001350694"

    stock\_ticker       VARCHAR(10) NOT NULL,

    shares\_held        BIGINT NOT NULL,

    market\_value\_usd   DECIMAL(18,2),

    pct\_portfolio      DECIMAL(6,3),

    shares\_change\_qoq  BIGINT,

    quarter\_end        DATE NOT NULL,

    source\_url         TEXT,

    recorded\_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT unique\_filer\_stock\_quarter UNIQUE (filer\_cik, stock\_ticker, quarter\_end)

);

SELECT create\_hypertable('institutional\_holdings', 'recorded\_at');

CREATE TABLE pipeline\_health\_events (

    id           UUID PRIMARY KEY DEFAULT gen\_random\_uuid(),

    scraper\_id   VARCHAR(100) NOT NULL,

    source\_name  VARCHAR(100) NOT NULL,

    event\_type   VARCHAR(30)  NOT NULL,   \-- success | dom\_shift\_detected | self\_heal\_triggered | self\_heal\_resolved | self\_heal\_failed

    message      TEXT,

    occurred\_at  TIMESTAMPTZ NOT NULL DEFAULT now()

);

SELECT create\_hypertable('pipeline\_health\_events', 'occurred\_at');

### 16.4 Neo4j Schema (Cypher)

This is also where the WhaleWisdom / institutional layer plugs into the same graph as the commodity ripple effect — one graph, not two separate systems:

CREATE CONSTRAINT commodity\_name IF NOT EXISTS FOR (c:Commodity) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT industry\_name  IF NOT EXISTS FOR (i:Industry)  REQUIRE i.name IS UNIQUE;

CREATE CONSTRAINT company\_ticker IF NOT EXISTS FOR (co:Company)  REQUIRE co.ticker IS UNIQUE;

CREATE CONSTRAINT filer\_cik      IF NOT EXISTS FOR (f:Filer)     REQUIRE f.cik IS UNIQUE;

// \--- Supply chain layer \---

MERGE (copper:Commodity {name: "Copper"})

MERGE (stator:Component {name: "Stator Coil"})

MERGE (ev:Industry {name: "EV Battery Manufacturing"})

MERGE (copper)-\[:REFINED\_INTO\]-\>(stator)

MERGE (stator)-\[:REQUIRED\_FOR\]-\>(ev)

MERGE (copper)-\[:IMPACTS\_COST\_OF {weight: 0.18}\]-\>(ev)

// \--- Institutional layer (the WhaleWisdom / 13F data lands here) \---

MERGE (bw:Filer {cik: "0001350694", name: "Bridgewater Associates"})

MERGE (nvda:Company {ticker: "NVDA", name: "Nvidia Corp"})

MERGE (bw)-\[:HOLDS {shares: 1200000, quarter: "2026-Q2", delta\_pct: 14.0}\]-\>(nvda)

// \--- The bridge: links institutional bets back to the commodities they're exposed to \---

MERGE (nvda)-\[:EXPOSED\_TO\]-\>(copper)

The `EXPOSED_TO` edge is what makes the Ripple Effect Graph and the Institutional Sentiment panel feel like *one product* instead of two features bolted together: clicking Copper can answer both "what industries does this hit" and "which hedge funds are positioned for that."

### 16.5 REST API Contract

| Endpoint | Method | Purpose |
| :---- | :---- | :---- |
| `/api/risk-map` | GET | Latest price deltas grouped by region/sector, for the heat map |
| `/api/commodities/:name/trend?days=30` | GET | Price history for one entity |
| `/api/graph/ripple/:commodity` | GET | Neo4j traversal \+ Gemini-generated explanation (§15 \#3) |
| `/api/institutional/holders/:ticker` | GET | Which filers hold this stock, with QoQ deltas |
| `/api/institutional/filer/:cik/holdings` | GET | Full holdings for one filer (e.g. Bridgewater) |
| `/api/pipeline-health` | GET (SSE stream) | Live feed powering the Self-Healing Audit Log |
| `/api/copilot/ask` | POST `{ question }` | Gemini-synthesized, cited answer (§15 \#5) |
| `/api/admin/scrapers/:id/heal` | POST | Manually trigger self-heal — this is your demo button |

### 16.6 Self-Healing Sequence

This is the exact loop, using the real Bright Data endpoints verified in §2:

sequenceDiagram

    participant Cron

    participant Ingest as Ingestion Service

    participant BD as Bright Data API

    participant Site as Target Website

    participant DB as TimescaleDB

    participant UI as Audit Log Stream

    Cron-\>\>Ingest: trigger job for collector\_id

    Ingest-\>\>BD: POST /dca/trigger\_immediate

    BD-\>\>Site: fetch page via Web Unlocker

    Site--\>\>BD: HTML or JSON response

    BD--\>\>Ingest: GET /dca/get\_result

    Ingest-\>\>Ingest: run health check on payload

    alt payload healthy

        Ingest-\>\>DB: upsert normalized rows

        Ingest-\>\>UI: log event \- success

    else DOM drift detected

        Ingest-\>\>UI: log event \- dom\_shift\_detected

        Ingest-\>\>BD: POST /dca/collectors/id/refactor\_template

        BD--\>\>Ingest: status pending\_answer, diff ready

        Ingest-\>\>BD: POST /resume\_automation\_job, auto\_save true

        BD--\>\>Ingest: status done, schema updated

        Ingest-\>\>BD: POST /dca/trigger\_immediate again

        BD--\>\>Ingest: healthy payload returned

        Ingest-\>\>DB: upsert normalized rows

        Ingest-\>\>UI: log event \- self\_heal\_resolved

    end

Health check logic (what decides "healthy" vs "drift detected"):

function isHealthy(payload: ScrapedRow\[\]): boolean {

  if (\!payload || payload.length \=== 0\) return false;

  const criticalFieldsMissing \= payload.some(

    (row) \=\> row.price \=== undefined || row.price \=== null

  );

  return \!criticalFieldsMissing;

}

### 16.7 Bright Data Collector Configs

One collector per scraped source, created via the CLI pattern verified in §2 (`brightdata scraper create <url> "<description>"`):

| Collector name | Target URL | Natural-language extraction prompt |
| :---- | :---- | :---- |
| `lme_copper_scraper` | `https://www.investing.com/commodities/copper` | "Extract the current price, daily percent change, and today's high and low for Copper futures." |
| `whalewisdom_13f_scraper` | `https://whalewisdom.com/filer/{slug}` | "Extract the list of stock holdings. For each holding, extract Stock Name, Ticker Symbol, Shares Held, Market Value in dollars, Percent of Portfolio, and Change versus Prior Quarter." |
| `fbx_scraper` | `https://data.freightos.com/` | "Extract the global FBX index value and each of the 12 tradelane index values with their day-over-day percent change." |
| `xsi_scraper` | `https://xsi.xeneta.com/` | "Extract the XSI global index value and the Far East, US, and Europe import and export sub-indices with percent change." |
| `fpma_scraper` | `https://fpma.apps.fao.org/giews/food-prices/tool/public/` | "Extract commodity name, country, market, price, currency, and date for the most recently updated domestic price series shown." |
| `oilprice_scraper` | `https://oilprice.com/oil-price-charts/` | "Extract benchmark name, price, unit, and percent change for each crude oil and refined product listed." |

Example self-heal trigger, called by the Ingestion Service when `isHealthy()` returns false:

async function triggerSelfHeal(collectorId: string, problemDescription: string) {

  const res \= await fetch(

    \`https://api.brightdata.com/dca/collectors/${collectorId}/refactor\_template\`,

    {

      method: "POST",

      headers: {

        Authorization: \`Bearer ${process.env.BRIGHTDATA\_API\_KEY}\`,

        "Content-Type": "application/json",

      },

      body: JSON.stringify({ prompt: problemDescription }),

    }

  );

  const { status } \= await res.json();

  if (status \=== "pending\_answer" && process.env.BRIGHTDATA\_AUTO\_APPROVE\_HEAL \=== "true") {

    await fetch("https://api.brightdata.com/resume\_automation\_job", {

      method: "POST",

      headers: {

        Authorization: \`Bearer ${process.env.BRIGHTDATA\_API\_KEY}\`,

        "Content-Type": "application/json",

      },

      body: JSON.stringify({ message: true, auto\_save: true }),

    });

  }

}

### 16.8 MCP Server Spec

Using the current, stable `@modelcontextprotocol/sdk` pattern (`registerTool`, not the deprecated `server.tool()`):

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { z } from "zod";

const server \= new McpServer({ name: "shadow-cpi", version: "1.0.0" });

server.registerTool(

  "get\_commodity\_price\_trend",

  {

    title: "Get Commodity Price Trend",

    description: "Latest public spot price and 30-day trend for a given commodity",

    inputSchema: { commodity: z.string() },

    outputSchema: { price: z.number(), currency: z.string(), trendPct: z.number() },

  },

  async ({ commodity }) \=\> {

    const result \= await fetchLatestPriceFromDB(commodity);

    const output \= { price: result.price, currency: result.currency, trendPct: result.trend };

    return {

      content: \[{ type: "text", text: JSON.stringify(output) }\],

      structuredContent: output,

    };

  }

);

server.registerTool(

  "analyze\_supply\_chain\_impact",

  {

    title: "Analyze Supply Chain Impact",

    description: "Downstream industries affected by a commodity price spike",

    inputSchema: { commodity: z.string() },

    outputSchema: { industries: z.array(z.string()) },

  },

  async ({ commodity }) \=\> {

    const graphResult \= await queryNeo4j(

      "MATCH (c:Commodity {name: $name})-\[:REQUIRED\_FOR\*1..2\]-\>(i:Industry) RETURN i.name AS name",

      { name: commodity }

    );

    const output \= { industries: graphResult.map((r: any) \=\> r.name) };

    return {

      content: \[{ type: "text", text: JSON.stringify(output) }\],

      structuredContent: output,

    };

  }

);

server.registerTool(

  "get\_institutional\_holders",

  {

    title: "Get Institutional Holders",

    description: "Hedge funds holding a stock, with quarter-over-quarter change",

    inputSchema: { ticker: z.string() },

    outputSchema: { holders: z.array(z.object({ filer: z.string(), deltaPct: z.number() })) },

  },

  async ({ ticker }) \=\> {

    const rows \= await fetchHoldersFromDB(ticker);

    const output \= { holders: rows };

    return {

      content: \[{ type: "text", text: JSON.stringify(output) }\],

      structuredContent: output,

    };

  }

);

server.registerTool(

  "ask\_shadow\_cpi\_copilot",

  {

    title: "Ask Shadow CPI Copilot",

    description: "Ask a free-form question grounded in live price and holdings data",

    inputSchema: { question: z.string() },

    outputSchema: { answer: z.string(), sources: z.array(z.string()) },

  },

  async ({ question }) \=\> {

    const output \= await runCopilot(question); // RAG over TimescaleDB \+ Neo4j, then Gemini

    return {

      content: \[{ type: "text", text: output.answer }\],

      structuredContent: output,

    };

  }

);

const transport \= new StdioServerTransport();

await server.connect(transport);

IDE configuration (e.g. `claude_desktop_config.json` or Claude Code's MCP config):

{

  "mcpServers": {

    "shadow-cpi": {

      "command": "node",

      "args": \["/path/to/apps/mcp-server/dist/index.js"\]

    }

  }

}

### 16.9 Gemini Prompt Templates

**Normalization (use case \#1):**

System: You normalize messy scraped commodity data into strict JSON. Return ONLY valid JSON matching this schema, no prose, no markdown fences:

{ "entity\_name": string, "price": number, "currency": string, "unit": string, "pct\_change\_1d": number|null }

User: Raw scraped payload:

{{raw\_payload}}

**Audit log narration (use case \#4):**

System: You write one-line status updates for a pipeline health dashboard, in the style:

"⚠️ \[HH:MM\] {source} layout changed. Scraping failed. → 🤖 \[HH:MM\] Self-Healing triggered. New table mapped. → ✅ \[HH:MM\] Data ingestion resumed."

Keep it under 200 characters. Use the real timestamps given.

User: Event: {{event\_json}}

**Copilot (use case \#5), always RAG-grounded:**

System: Answer the user's question using ONLY the data provided below. Cite which source or filing each fact came from. If the data doesn't cover the question, say so plainly instead of guessing.

User question: {{question}}

Retrieved price data: {{price\_rows}}

Retrieved graph context: {{graph\_rows}}

Retrieved institutional data: {{holdings\_rows}}

### 16.10 Cron / Orchestration Schedule

| Job | Frequency |
| :---- | :---- |
| Freight (FBX, XSI) | Every 6 hours |
| Energy — EIA official API | Every 1 hour |
| Energy/metals — scraped (copper, oilprice) | Every 2 hours |
| Agriculture — USDA official API | Daily |
| Agriculture — FAO FPMA (scraped) | Weekly |
| Institutional — SEC EDGAR check for new filings | Every 1 hour |
| Institutional — WhaleWisdom scrape | On-demand / demo trigger (see §17) |
| Self-heal watchdog | Runs immediately after every collector job, inline |
| Anomaly flagging (Gemini use case \#6) | Nightly batch |

### 16.11 Frontend Page Map (Next.js App Router)

apps/web/app/

├── (dashboard)/

│   ├── risk-map/page.tsx

│   ├── ripple/\[commodity\]/page.tsx

│   ├── institutional/page.tsx

│   ├── pipeline-health/page.tsx

│   └── copilot/page.tsx

└── api/

    └── ... route handlers mirroring §16.5, or proxy to apps/api

Build them in this order — it matches §7's user flow, so even a half-finished build still demos coherently top to bottom: `risk-map` → `ripple` → `institutional` → `pipeline-health` → `copilot`.

---

## 17\. Deep-Dive: The WhaleWisdom Example

This is the exact scenario you asked about — a site that anti-bot-protects itself *and* changes its DOM. Here's the full solution, formalized.

### 17.1 The two-path architecture

| Path | Source | Why it exists |
| :---- | :---- | :---- |
| **Primary (production)** | SEC EDGAR direct (§8.4) | 100% free, official, zero anti-bot, zero DOM to break. This is what you'd actually run at scale. |
| **Demo (judge-facing)** | WhaleWisdom via Bright Data self-healing | WhaleWisdom's pre-parsed UI and deltas are genuinely nicer to look at *and* it's the site that actually has the anti-bot \+ shifting-DOM problem your hackathon brief is scored on solving. Use this to *show* resilience, not as your only data path. |

You are not choosing one over the other — SEC EDGAR keeps the app correct and running 24/7; the WhaleWisdom scraper is what you break on stage.

### 17.2 Step-by-step (as implemented in §16.7–§16.8)

1. **Create the collector** with a plain-language prompt (§16.7 table) instead of hardcoded CSS selectors.  
2. **Anti-bot is handled for you** — Bright Data routes the request through its Web Unlocker/residential proxy network; you never write CAPTCHA-solving or user-agent-rotation code.  
3. **DOM drift is handled by self-healing** — the health check in §16.6 catches the empty/null payload, and `refactor_template` \+ `resume_automation_job` (§16.7 code) fix it without you touching a selector.  
4. **Everything lands in the same graph** as the commodity data via the `EXPOSED_TO` edge (§16.4) — so "Bridgewater bought more Nvidia" and "copper is up 8%" are one connected story, not two separate tabs.

### 17.3 Demo script: "simulate the break" (for §12's finale)

Don't rely on WhaleWisdom actually breaking live on stage — script a reliable, repeatable version:

1. Save one real, successful scrape of a WhaleWisdom filer page as a local HTML fixture.  
2. Write a small script that renames the fixture's table/row CSS classes (e.g. `.fund-holding-table-row` → `.holding-item-2026`) to simulate a redesign.  
3. Point a local mock endpoint at the mutated fixture; point the collector at it instead of the live site for this demo run.  
4. Run the collector — the health check correctly reports `dom_shift_detected`.  
5. Trigger `refactor_template` live in front of the judges; show the diff Bright Data proposes.  
6. Show the recovered data flowing and the Pipeline Health log completing its `⚠️ → 🤖 → ✅` sequence.

This gives you a demo that is *real* (real API calls, real AI-generated fix) but *reliable* (you control exactly when and how it breaks).

---

## 18\. Appendix — Sample Payloads

**Sample normalized row (`commodity_prices`):**

{

  "entity\_name": "Copper",

  "sector": "metals",

  "price": 4.52,

  "currency": "USD",

  "unit": "lb",

  "pct\_change\_1d": 1.8,

  "recorded\_at": "2026-08-15T09:00:00Z",

  "source\_name": "investing.com",

  "source\_url": "https://www.investing.com/commodities/copper",

  "ingestion\_method": "brightdata\_scrape"

}

**Sample MCP tool call/response (`get_institutional_holders`):**

// request

{ "ticker": "NVDA" }

// response.structuredContent

{

  "holders": \[

    { "filer": "Bridgewater Associates", "deltaPct": 14.0 },

    { "filer": "Berkshire Hathaway", "deltaPct": \-3.2 }

  \]

}

**Sample Pipeline Health event → Gemini narration output:**

⚠️ \[03:00\] WhaleWisdom layout changed. Scraping failed. → 🤖 \[03:02\] Self-Healing triggered. New table mapped. → ✅ \[03:03\] Data ingestion resumed.

## 19\. APPENDIX A: UNIFIED FINANCIAL, SEC & COMMODITY ARCHITECTURE

### Architecture Diagram: [Mermaid Preview](https://mermaid.live/view#pako:eNqVVw1v2kgQ_SsrV41SyRBsA6XoVMnBBLhCoBja6i6n02IP9l7MLlqvm3BR_vvN-iMhQHsNUiy8zLydefNmdvNgBCIEo2tEkm5jsvBu5A0n-Hn7lvhqlzAeEQ_WjDPFBE-rX4OEpimuk1RkMgBtCWTNkqT7xgILbDBTJcUtdN90Pqyaa1q-1u5YqOKuvb03A5EI2X0ThGF73TyGVVnIxAvYjtWxW0-wa7pyOu9fCxsDTfZBHcuxm81nUKezop3Xxyok_CRU2gaHWq9FpdvtT1gNVrS9_pX098pp1cmc3pEFlREo4lFFiZ9X76mqabYqZOBPl_Ne3__zxkCnUw7GX5WP_vgWWvr9Hul7A3dOzq1G7dMFPj6_OzS00fBrTBP4ytJQbNDUuSIzIdVaJEykR_YO2rucZzSZwxbN0nqgvWbeFapTUgXR7siniT5L33PJBemP9PPKneJzPOnjcyFpiJruB4KLDQv2MwEevqgCpmX6tuk7pt_c1_kBrXadXEoWxRVDATIIEsPTCiZzgSW0jgieT8d9TdrPnc8L765eZ1tFehKobkNyRkY8glR_P0x_bv098vq6HgUGvqD5V1g9gbuz0W8refHxfKSbmiYV-hnxIYEA1fy00Qnw_rd-T6OXYP17CLI8pj6PGIcSeYaJqxzCJC5XrHYpFLncbZFWk3g7TpF7MkfGQWI1TudAarWP1Y4_rFFhapZm-3PjoEw5vzO2BRxpQHqCc0wV46tMSskfbrqH4NTJRCBlQoes2Qpi2FDyhSYspPtQVTAa6os7ftBs5aZnZIgDSMWVj5AFXb0Ygtu0CPEzap2pnUmusyRJ94syZEo3yONBWM3_159NzhFlXdO769gvJeVB_O6kKnWHOr-gSrtL3EzpLhJZSl7AF0o4LOpQ6308nhBvOsHSp0EGxI2Aq4KDGZUppLgvDjROhovJGHO_YjxE8JitFYTlIDrC1RE_SSrD0AbAQT6zO4eoWED4MoWe7198m1GsRMXu0egZOs89hB1DhkLV0COIC9DlNiwAS270xrpaC-QtAonChJrMjhroJSG5Qob2y2yKReeHih9a5tA2h87zYXYgiGdBYvWxN3lU_YhiRHSCeVWauqIsySTgYNRVyYm-MYoInoYWbpU7YUZFt0OZdUh-F6vS_HTLtOrEE3ccjymgGyRfSBpBPr1CuN8L7PngWUzn7kCPL5T1gm2g5uOEyAtX-X7i4i6BEL9f0hQO-PUurT_Pb4yZSFWEh_LnsR75CJMGeOZ4l6XUJAsA20kf3DvdYdirV0xLV6vg3QGgrQG30feCMB1HOeQm3pmL3sXxRIrzifTijN-egnE0jJ9tt8mu1osp42SQZ1wF1ccpqXQ0Eypv8bidQ5LXMI3Z9iXekSIwaRPjxD9n7zKyX4qnwufa0EdnFiise5g3eFlChHmlvf1Ke-dAHu16MQF047oDzSXSw4JCu2O6A3kkkN702l9OZovR9BpF0joC0G8XyxQ7csQVyDU9vq2gJboOYIOXWqSZpjjU84G-D7V_mpVdZOpTQ8G9Iv6OqxhSlubl4vkk35EeK068o1GyHOF-1-hY_yfVGGm2wfg8msYrQWVYbOLHNBR3pIej5owUCnUTkOoIbdKbIRw-cXbJ71AOOXeEyPpmU2RBFkIkOQVI24ugDrqlaF53cKD508vOqWXNll5ejk6tYpw_PrvdgbkcmTqV6rZrmPiPCAuNLioITAN52lD9ajxoxxsDad9gz3fxawhrmiU4rm74I7ptKf9DiE3lKUUWxUZ3TZMU37J8WnuMIhvPJvn1oycyroxuq5FDGN0H497o2q1OvdV2mp0PnUan2e40TWNndK1mp97E9_dtu2G3PrRb9qNp_JtvatcbjXarbVlNu9FsNzqtx_8A654l0w)

1. Unified System Data Flow & Ingestion Matrix

| Source / Endpoint | Access Method | Primary Function | Data Pipeline Layer |
| :---- | :---- | :---- | :---- |
| SEC Tickers (company\_tickers.json) | Public SEC Endpoint | Map Ticker/Name to 10-digit CIK | Identity Resolution Pipeline |
| SEC EDGAR (data.sec.gov) | REST API (User-Agent Auth) | Fetch 10-K, 10-Q, 13F-HR XML tables | Core SEC Financial Ingestion |
| WhaleWisdom | Selenium / Playwright | Extract 13F quarterly portfolio holdings | Institutional Scraping Engine |
| USDA AMS My Market News | REST API (/services/v3.1/) | Livestock, Grain, Dairy market reports | Tier-1 Agri Ingestion |
| EIA Open Data (api.eia.gov/v2) | REST API Key | Petroleum, Crude spot & inventory | Tier-1 Energy Ingestion |
| FAO GIEWS / FPMA | Scraping / Backend API | Global Cereal prices & IFPA warnings | Tier-2 Food Security Pipeline |
| TradingEconomics | Scraping / API | Macro, Bonds, Equities, Currencies | Tier-2 Macro & Yield Engine |
| OilPrice.com / LME | Headless Scraping | Spot Crude & Industrial Metal prices | Tier-3 Industrial Metals & Energy |

2.   
   End-to-End Infrastructure Architecture Diagram

┌────────────────────────────────────────────────────────────────────────────────────────┐

│ \[ MULTI-SOURCE INGESTION LAYER \] │

│ │

│ ┌──────────────────┐ ┌────────────────────┐ ┌──────────────────┐ ┌──────────────┐ │

│ │ SEC EDGAR API │ │ WhaleWisdom 13F │ │ USDA AMS & EIA │ │ Macro/Metals │ │

│ │ \- Ticker \-\> CIK │ │ \- Portfolio Scraper│ │ \- Agri Reports │ │ \- FAO GIEWS │ │

│ │ \- 10-K, 10-Q, 13F│ │ \- Sector Allocations│ │ \- Energy APIs │ │ \- LME/Oil │ │

│ └────────┬─────────┘ └─────────┬──────────┘ └────────┬─────────┘ └──────┬───────┘ │

│ │ │ │ │ │

│ ▼ ▼ ▼ ▼ │

│ ┌──────────────────┐ ┌────────────────────┐ ┌──────────────────┐ ┌──────────────┐ │

│ │ SEC Fetcher │ │ Dynamic Vue DOM │ │ Direct REST API │ │ Headless │ │

│ │ (User-Agent Auth)│ │ Scraper (Selenium) │ │ Client (Aiohttp) │ │ Scraper │ │

│ └────────┬─────────┘ └─────────┬──────────┘ └────────┬─────────┘ └──────┬───────┘ │

│ │ │ │ │ │

│ └──────────────────────┼──────────────────────┴───────────────────┘ │

└──────────────────────────────────┼─────────────────────────────────────────────────────┘

│

▼

┌──────────────────────────────────┐

│ KAFKA / RABBITMQ MESSAGE BUS │

│ (Raw Data Payload Queuing) │

└────────────────┬─────────────────┘

│

▼

┌──────────────────────────────────┐

│ NORMALIZATION & PIPELINE ENGINE │

│ \- CIK 10-digit Pad (zfill(10)) │

│ \- Ticker & Sector Mapping │

│ \- Data Anomaly & Range Filter │

└────────────────┬─────────────────┘

│

▼

┌──────────────────────────────────┐

│ PostgreSQL / TimescaleDB │

│ \- sec\_filings & 13f\_holdings │

│ \- commodity\_spot\_series │

└────────────────┬─────────────────┘

\================================================================================

APPENDIX B: CORE AGENTIC RAG SYSTEM & CITATION ARCHITECTURE

1. Agentic RAG Workflow Overview

The Agentic RAG System acts as the intelligence layer operating over the ingested financial, commodity, macro, and SEC datasets. Rather than using simple vector search, an autonomous Agentic Workflow manages query routing, dynamic context retrieval, citation verification, and answer generation.

┌────────────────────────────────────────────────────────────────────────────────────────┐

│ USER QUERY / ANALYST PROMPT │

└───────────────────────────────────────────┬────────────────────────────────────────────┘

│

▼

┌────────────────────────────────────────────────────────────────────────────────────────┐

│ ROUTER AGENT (Intent Classifier) │

└───────────────────────────────────────────┬────────────────────────────────────────────┘

│

┌──────────────────────────────────┼──────────────────────────────────┐

│ (SEC / Corporate) │ (Commodity / Spot) │ (Macro / Yields)

▼ ▼ ▼

┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐

│ SEC & 13F │ │ Commodity │ │ Macro & Market │

│ Retriever │ │ Retriever │ │ Retriever │

│ \- 10-K/10-Q Chunk│ │ \- USDA/EIA Series│ │ \- Bond Yields │

│ \- 13F Holdings │ │ \- FAO IFPA Alerts│ │ \- Stock Indices │

└────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘

│ │ │

└──────────────────────────────────┼──────────────────────────────────┘

│

▼

┌────────────────────────────────────────────────────────────────────────────────────────┐

│ VECTOR \+ HYBRID CONTEXT STORE │

│ (PostgreSQL / pgvector) │

└───────────────────────────────────────────┬────────────────────────────────────────────┘

│

▼

┌────────────────────────────────────────────────────────────────────────────────────────┐

│ CITATION ENFORCEMENT ENGINE │

│ \- Exact Source URL Mapping │

│ \- Metadata & Timestamp Binding │

└───────────────────────────────────────────┬────────────────────────────────────────────┘

│

▼

┌────────────────────────────────────────────────────────────────────────────────────────┐

│ GENERATIVE ANSWER \+ CITATIONS │

│ \- Grounded Insight Output │

│ \- Explicit Source References │

└────────────────────────────────────────────────────────────────────────────────────────┘

2. Strict Citation Engine Requirements

To guarantee factual accuracy and prevent hallucinations, every response generated by the Agentic RAG engine must comply with the following citation standards:

• Source Link Binding: Every statement, price metric, or holding percentage extracted from scraped context or SEC filings must be immediately followed by an inline, hyperlinked reference URL to the primary source.

• Metadata Transparency: Citations must include underlying raw metadata (e.g., Filing Accession Number, CIK, API Endpoint URL, or Scraped Webpage URL).

• Multi-Source Cross-Verification: When comparing WhaleWisdom 13F scraping results against SEC EDGAR XML filings, the RAG agent must cite both sources and flag any discrepancy in share counts or reported values.

Example Verified Agent Response Format:

"What is Fundsmith's position in Marriott International (MAR) and how does it compare to current commodity trends in consumer discretionary?"

Generated Answer Output:

* Fundsmith LLC holds 2,585,757 shares of Marriott International Inc (MAR), representing approximately 7.02% of their portfolio \[WhaleWisdom Source: [https://whalewisdom.com/filer/fundsmith-llp](https://whalewisdom.com/filer/fundsmith-llp)\] \[SEC 13F-HR CIK: 0001045810: [https://www.sec.gov/edgar/browse/?CIK=0001045810](https://www.sec.gov/edgar/browse/?CIK=0001045810)\].  
* The sector classification for MAR is Consumer Discretionary, which has seen direct impacts from fluctuating fuel and energy transportation overhead \[EIA Spot Data API: [https://api.eia.gov/v2/petroleum/pri/spt/data](https://api.eia.gov/v2/petroleum/pri/spt/data)\].

## 20\. APPENDIX B: MASTER DATA SOURCE & REFERENCE LINK DIRECTORY

1. Regulatory Financial & SEC Identity Services

• SEC Company Tickers Mapping (CIK Resolution): [https://www.sec.gov/files/company\_tickers.json](https://www.sec.gov/files/company_tickers.json)

• Institutional Portfolio Scraping Source (WhaleWisdom): [https://whalewisdom.com/filer/fundsmith-llp](https://whalewisdom.com/filer/fundsmith-llp)

2. USDA Agricultural Market API Endpoints & Links

• USDA AMS My Market News API Documentation: [https://marsapi.ams.usda.gov/services/help](https://marsapi.ams.usda.gov/services/help)

• USDA AMS Documentation (Extended): [https://marsapi.ams.usda.gov/services/help/more](https://www.google.com/search?q=https://marsapi.ams.usda.gov/services/help/more)

• USDA AMS API Public Endpoints:

* [https://marsapi.ams.usda.gov/services/v3.1/public/listCorrectedReports?format=](https://www.google.com/search?q=https://marsapi.ams.usda.gov/services/v3.1/public/listCorrectedReports%3Fformat%3D)  
* [https://marsapi.ams.usda.gov/services/v3.1/public/listCorrectedReports/](https://www.google.com/search?q=https://marsapi.ams.usda.gov/services/v3.1/public/listCorrectedReports/){nbrOfDays}?format=  
* [https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReport/](https://www.google.com/search?q=https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReport/){slug\_id}?format=  
* [https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReports?format=](https://www.google.com/search?q=https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReports%3Fformat%3D)  
* [https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReports/](https://www.google.com/search?q=https://marsapi.ams.usda.gov/services/v3.1/public/listPublishedReports/){nbrOfDays}?format=

• USDA MyMarketNews Main Portals:

* [https://mymarketnews.ams.usda.gov/mymarketnews-api/reports](https://mymarketnews.ams.usda.gov/mymarketnews-api/reports)  
* [https://mymarketnews.ams.usda.gov/marketnews-home](https://mymarketnews.ams.usda.gov/marketnews-home)  
3. Energy & Petroleum APIs and Sources

• EIA Petroleum Data Directory: [https://www.eia.gov/petroleum/data.php](https://www.eia.gov/petroleum/data.php)

• EIA API v2 Endpoint (Requires Key): [https://api.eia.gov/v2/petroleum/pri/spt/data](https://api.eia.gov/v2/petroleum/pri/spt/data)

• EIA API Registration Page: [https://www.eia.gov/opendata/register.php](https://www.eia.gov/opendata/register.php)

• Oil Price Live Charts: [https://oilprice.com/oil-price-charts/](https://oilprice.com/oil-price-charts/)

4. Industrial Metals & Commodities

• Investing.com LME Daily Index: [https://www.investing.com/indices/lme-daily](https://www.investing.com/indices/lme-daily)

• TradingEconomics Commodities: [https://tradingeconomics.com/commodities](https://tradingeconomics.com/commodities)

5. Global Food Security & Agriculture (FAO GIEWS / FPMA)

• FAO GIEWS Home Portal: [https://www.fao.org/giews/food-prices/home/en/](https://www.fao.org/giews/food-prices/home/en/)

• FAO FPMA International Dashboard Tool: [https://fpma.fao.org/giews/fpmat4/global/\#/dashboard/tool/international](https://fpma.fao.org/giews/fpmat4/global/#/dashboard/tool/international)

• FAO FPMA Domestic Dashboard Tool: [https://fpma.fao.org/giews/fpmat4/global/\#/dashboard/tool/domestic](https://fpma.fao.org/giews/fpmat4/global/#/dashboard/tool/domestic)

6. Macroeconomics, Equities, Bonds & Currencies

• TradingEconomics Main Dashboard: [https://tradingeconomics.com/](https://tradingeconomics.com/)

• TradingEconomics Stocks: [https://tradingeconomics.com/stocks](https://tradingeconomics.com/stocks)

• TradingEconomics Bonds: [https://tradingeconomics.com/bonds](https://tradingeconomics.com/bonds)

• TradingEconomics Currencies: [https://tradingeconomics.com/currencies](https://tradingeconomics.com/currencies)

## 21\. APPENDIX C: ADDON MODULE \- GLOBAL SHAREHOLDER ANNUAL REPORTS INTEGRATION

1. **Overview & Value Proposition**

**To extend intelligence coverage beyond US SEC EDGAR boundaries, the platform incorporates an unstructured document ingestion module for AnnualReports.com.**

**Key Business Values Added: • International Coverage Expansion: Accesses financial disclosures for over 10,000 public companies across major global stock exchanges (LSE, TSX, ASX, NYSE, NASDAQ). • Qualitative Strategy Context: Captures qualitative narrative disclosures (CEO Address, Strategic Market Outlook, Multi-year Capital Allocation Plans, and ESG commitments) that are absent or legally restricted in standard SEC 10-K/10-Q filings. • Cross-Border Macro Alignment: Enables the Agentic RAG system to align macro-level commodity fluctuations (e.g., LME metal indices, EIA petroleum prices) with global corporate leadership commentary.**

2. **Source Endpoint & Pipeline Classification**

**Source Name: AnnualReports.com Global Directory Directory Link: [https://www.annualreports.com/](https://www.annualreports.com/) Company Index Link: [https://www.annualreports.com/Companies](https://www.annualreports.com/Companies)**

**Pipeline Role: Tier-2 Unstructured PDF & Qualitative Document Ingestion Ingestion Method: Web Crawler / PDF Download Worker (PyMuPDF / Unstructured Engine Parsing)**

3. **Agentic RAG Multi-Document Citation Standard**

**When generating responses that combine raw regulatory SEC data and qualitative AnnualReports.com PDFs, the RAG agent must cite both distinct document types:**

**Example Query: "How is BHP/Rio Tinto addressing global iron ore pricing trends and supply risks?"**

**Example Generated Answer Output:**

* **BHP Group's executive leadership highlights an expected shift in industrial steel demand and localized supply chain constraints across global markets \[AnnualReports.com BHP PDF Source: [https://www.annualreports.com/Company/bhp-billiton-ltd](https://www.annualreports.com/Company/bhp-billiton-ltd)\].**  
* **Concurrently, daily industrial metals benchmarks indicate a 0.4% contraction in LME cash prices \[LME Daily Index: [https://www.investing.com/indices/lme-daily](https://www.investing.com/indices/lme-daily)\].**

