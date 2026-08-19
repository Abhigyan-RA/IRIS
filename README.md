# Shadow CPI

Official inflation data is published monthly and describes prices from weeks ago.
Shadow CPI watches the underlying prices instead, every day: ocean freight rates,
energy and metal spot prices, bulk crop prices, and the stock holdings that large
investment managers disclose each quarter. It collects them from around ten public
sources, stores price history in TimescaleDB and supply-chain relationships in
Neo4j, and answers two kinds of question: what is getting more expensive, and what
does that affect downstream.

Two front doors sit on the same data: a Next.js dashboard for people, and an MCP
server so AI agents and IDEs can query it directly. Gemini handles the messy parts:
turning scraped text into clean records, explaining why a price move matters, and
answering free-form questions with citations back to the source.

Full product scope, data sources, database schema, and API contracts live in
[SHADOW_CPI_PRD_AND_ARCHITECTURE.md](./SHADOW_CPI_PRD_AND_ARCHITECTURE.md).

## Prerequisites

- Node.js 22 or newer, and npm 10 or newer
- Python 3.11 or newer (the backend is FastAPI)
- A container runtime with Compose support, for the local databases. Docker and Podman
  both work; the commands below show Docker, and `podman compose` is a drop-in
  replacement.
- Credentials:
  - Google Gemini API key (required)
  - Bright Data API key (required) for the sources that have no official API
  - EIA, USDA, and an SEC contact string (optional and free, but recommended: they
    replace scraping for three of the four data categories)
  - Neo4j AuraDB (optional; the Docker Neo4j below is enough for development)

Every variable, and where to get it, is documented in
[.env.example](./.env.example).

## Setup

```bash
git clone <repository-url> shadow-cpi
cd shadow-cpi

# 1. Configuration
cp .env.example .env      # then fill in the two required keys

# 2. Local databases: TimescaleDB, Neo4j, Redis
docker compose -f infra/docker-compose.yml up -d

# 3. Dashboard dependencies
npm install

# 4. Backend dependencies (uv shown; plain python -m venv and pip also work)
cd backend
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"   # macOS/Linux: .venv/bin/python
cd ..

# 5. Create the database schema and load the starting graph.
#    Safe to re-run; it applies only what is missing.
backend/.venv/Scripts/python -m shadow_cpi.db.prepare
```

If one of the ports is already in use, which is common on a machine that already runs
PostgreSQL, set `POSTGRES_HOST_PORT` (or the Neo4j and Redis equivalents) in `.env` and
point the connection strings at the port you chose. Do not stop the service you already
depend on.

To confirm both databases really work, rather than trusting the test suite's fakes:

```bash
backend/.venv/Scripts/python -m shadow_cpi.db.smoke_check
```

It writes one row of each kind, reads them back, checks that a repeated write updates
rather than duplicates, runs a graph traversal, and deletes everything it wrote.

## Running the app

```bash
# Dashboard on http://localhost:3000
npm run dev

# API on http://localhost:8000, with docs at /docs
backend/.venv/Scripts/python -m shadow_cpi.api.main

# MCP server, for AI agents and IDEs (speaks over standard input and output)
backend/.venv/Scripts/python -m shadow_cpi.mcp_server.main
```

### What the API offers

| Endpoint                                      | Purpose                                              |
| --------------------------------------------- | ---------------------------------------------------- |
| `GET /health`                                 | Liveness, environment, and version                   |
| `GET /api/risk-map`                           | Newest price per tracked entity, grouped by category |
| `GET /api/commodities/{name}/trend?days=30`   | Price history for one entity                         |
| `GET /api/graph/ripple/{commodity}?depth=2`   | What a commodity feeds into, and who is exposed      |
| `GET /api/institutional/overview`             | Latest stored funds, stocks, moves, and enrichment   |
| `GET /api/institutional/holders/{ticker}`     | Funds reporting a position in a stock                |
| `GET /api/institutional/filer/{cik}/holdings` | One fund's reported portfolio                        |
| `GET /api/pipeline-health`                    | Recent collector activity                            |
| `GET /api/pipeline-health/stream`             | The same feed, live                                  |
| `POST /api/copilot/ask`                       | A question answered from stored data, with citations |
| `POST /api/admin/scrapers/{id}/heal`          | Run one collector now and repair it if needed        |

The repair endpoint requires an `X-Cron-Secret` header matching `CRON_SECRET`,
because it spends money at the scraping provider and sends traffic to a live site.

To connect the MCP server to an editor or agent runtime:

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

It offers five tools: `get_commodity_price_trend`, `analyze_supply_chain_impact`,
`get_institutional_holders`, `check_data_freshness`, and `ask_shadow_cpi_copilot`.
Run it with the same environment as the API, since it reads the same databases.

### What the copilot will and will not answer

Every answer is built from stored records and cites them. A question naming an entity is
answered from that entity's history; a question naming none, such as "what moved most this
week", is answered from every tracked price rather than refused on the technicality that no
name was spelled out. Where a figure has not been collected, the answer says so instead of
estimating: asked about a weekly move before a week of readings exists, it reports that the
weekly change is not available and gives the daily one.

## Collecting data

Nothing appears on the dashboard until a source has run. Collect once, now:

```bash
backend/.venv/Scripts/python -m shadow_cpi.collect            # every source
backend/.venv/Scripts/python -m shadow_cpi.collect --list      # what is ready, and what is not
backend/.venv/Scripts/python -m shadow_cpi.collect --source sec_edgar_13f
```

Or keep collecting on a timetable, which runs once immediately and then at the rate each
source publishes:

```bash
backend/.venv/Scripts/python -m shadow_cpi.orchestration.scheduler
```

What works with which credentials:

| Source                                                                        | Needs                                                         | Without it                       |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------- | -------------------------------- |
| `sec_edgar_13f`                                                               | nothing, only a contact address in `SEC_EDGAR_USER_AGENT`     | works out of the box             |
| `whalewisdom_13f_scraper`                                                     | a single-page Scraper Studio collector and explicit watchlist | skipped; SEC holdings still work |
| `eia_wti_page`, `eia_brent_page`                                              | nothing; read from public government pages                    | work out of the box              |
| `eia_petroleum_spot`                                                          | free `EIA_API_KEY`                                            | skipped                          |
| `usda_grain_prices`                                                           | free `USDA_MARS_API_KEY`                                      | skipped                          |
| `lme_copper_scraper`, `fbx_scraper`, `baltic_dry_scraper`, `oilprice_scraper` | a Scraper Studio collector in `SCRAPER_STUDIO_COLLECTORS`     | skipped                          |

A source that cannot run is skipped and says so, rather than failing quietly. Every run,
including a skip, is visible on the pipeline health screen.

Institutional holdings follow a stricter provenance boundary. SEC EDGAR is the authoritative
ledger for shares and market value. The dashboard shows every fund, stock, and position from
the newest SEC quarter currently stored, subject to the API's stated response caps. WhaleWisdom
is optional human-readable enrichment for an explicit fund watchlist only; it never overwrites
SEC rows, discovers additional filer pages, or claims exhaustive site coverage. Form 13F data is
quarterly, delayed, and long-only, so the screen states the reporting quarter and this limitation.

### What gets stored, and what does not

A collected page is rarely one number. The container freight page publishes a global index and
a price for each of a dozen trade lanes; the oil page lists several benchmarks. Two rules decide
what is kept, and both come from looking at what the collectors actually return:

- **A value that differs per row is stored under its own name.** Each freight lane becomes its
  own tracked entity, such as `FBX03_China_to_North_America_East_Coast`, because an importer
  cares what their route costs rather than what the average costs.
- **A value repeated across rows is stored once.** The oil page shows six benchmark links but
  the same price beside all of them, so storing one per benchmark would claim Brent trades at
  WTI's price. Repeats are collected once and the run reports one price, not six.

Most pages publish a daily change and no weekly one. The weekly figure is worked out from the
readings already stored, once enough of them exist, and a figure the page published itself is
never overwritten. Until there is history to compare against, a change stays empty and the
screen says so rather than showing a confident zero.

### When something goes wrong on screen

Every failure is described in one place and in plain language: what happened, what the reader
can do, and whether trying again could help. A stopped API says the service cannot be reached
and how to start it; a missing entity says nothing has been recorded for it yet; a reply that
does not match the schema says the dashboard and API are different versions. The underlying
error is kept behind a "Technical detail" disclosure and written to the console, so debugging
loses nothing. Failures that empty a screen are explained in place, and failures a reader can
ignore appear as a notice that does not disappear on a timer.

### Building a scraper for a site that blocks readers

The commercial sites actively block automated readers, so they are collected by Bright Data
Scraper Studio. A collector there is a scraper whose code the AI Agent writes from one
sentence describing the data, running on Bright Data's unblocking infrastructure. Build one
from the terminal:

```bash
npx -p @brightdata/cli bdata scraper create \
  https://www.investing.com/commodities/copper \
  "Extract the current copper futures price in USD per pound and its daily percent change"
```

It prints a collector identifier such as `c_mswnopw72dyj64c7s3`. Add it to
`SCRAPER_STUDIO_COLLECTORS` as `source_id=collector_id` and that source starts collecting.
The identifier is a stable handle: healing a scraper keeps it, so nothing downstream changes
when a site is redesigned. Set `BRIGHTDATA_API_KEY` and the CLI needs no login step.

### When a site changes

Every collector defines its own output fields, so the health check asks whether the value can
be found at the paths a source declares, rather than whether a field with a fixed name
exists. When no row carries the value, the run is treated as a changed site:

1. `[WARNING]` the site reads differently, naming what is missing.
2. Gemini writes a description of what broke, in plain language.
3. That description goes to Scraper Studio's self-healing, which rewrites the scraper's
   parsing code and returns a draft.
4. `[AUTO-HEALING]` the draft is accepted, automatically or after review, depending on
   `BRIGHTDATA_AUTO_APPROVE_HEAL`.
5. The collector runs again: `[RESOLVED]` if the values are back, `[FAILED]` if not.

No step involves a CSS selector, which is what makes a redesign recoverable. A repair can
also be triggered by hand:

```bash
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  http://localhost:8000/api/admin/scrapers/lme_copper_scraper/heal
```

## Running tests

```bash
# Backend
cd backend
.venv/Scripts/python -m pytest                                   # all tests
.venv/Scripts/python -m pytest --cov --cov-report=term-missing    # with coverage

# Dashboard
npm run test            # unit and component tests
npm run test:coverage   # with coverage
npm run test:e2e        # the one end-to-end journey, in a real browser
npm run storybook       # component explorer on http://localhost:6006
```

Both suites fail if coverage drops below 80 percent, and the backend suite fails if
any test is skipped. The end-to-end test starts a stub API with fixed replies and
builds the dashboard against it, so it needs no databases and asserts exact figures.

## How the repository is organised

```
apps/web/     Next.js dashboard, component tests, Storybook stories, end-to-end test
backend/      FastAPI service: ingestion, normalization, REST API, MCP server
infra/        Docker Compose for TimescaleDB, Neo4j, Redis
designs/      Design references for the dashboard screens
```

`backend/README.md` explains what lives in each backend package.

## How it is put together

A few decisions explain most of the code:

- **Every layer depends on interfaces, not implementations.** Repositories, HTTP
  clients, the model client, and the scraping provider are all passed in. That is why
  the test suite needs no database, no network, and no API keys.
- **External input is validated where it enters.** Scraped payloads and API replies
  are checked against a schema before anything else sees them, and invalid data is
  rejected rather than repaired. The dashboard does the same with API replies, because
  it is deployed separately and can be a different version.
- **Numbers keep their precision.** Prices are decimals in the database and strings in
  transit, all the way to the screen. Nothing converts them to floating point on the
  way to a reader who may be about to sign a contract.
- **Nothing on screen is unattributed.** Every stored price carries its source URL and
  how it was collected, and every screen and copilot answer shows it.
- **Failures are visible.** A stale figure is labelled stale, a broken collector is
  shown as broken, and a screen that cannot reach the API says so instead of rendering
  empty.

## Security

The measures below are asserted by tests in `backend/tests/test_security_posture.py`,
so a change that breaks one fails the build.

- Secrets come from environment variables, read in exactly one module, and are held as
  secret values that render as asterisks if printed or logged. No secret appears in any
  API response, in the OpenAPI schema, or in an error message.
- Only variables prefixed `NEXT_PUBLIC_` are read by the dashboard, so nothing else can
  reach the browser bundle.
- Every external input is schema-validated at its boundary: pydantic in the backend,
  zod in the dashboard.
- SQL uses bound parameters only. Cypher cannot parameterize labels, relationship types,
  or path length, so each of those is checked against a fixed allow-list first.
- Filings are parsed with a hardened XML reader that refuses document type definitions,
  because a filing could otherwise declare entities that expand until memory runs out.
- Every public route is rate limited per client address, and the copilot endpoint has a
  stricter allowance of its own because each call costs money.
- The privileged repair endpoint requires a shared secret, compared in constant time.
- Standard security headers on every response, CORS restricted to named origins with
  wildcards refused, and HTTPS required outside local development.
- SEC EDGAR requests identify themselves with a contact address, as that service
  requires.
- `npm audit` runs in CI and blocks on high-severity findings.

## Development workflow

- Tests are written before the code they describe.
- Secrets come from environment variables only, and are never logged or returned in a
  response.
- Status text uses labels such as `[WARNING]`, `[AUTO-HEALING]`, and `[RESOLVED]`
  rather than emoji, and the UI uses named icon components. A check enforces this.
- A pre-commit hook formats staged files and runs linting, type checking, and the emoji
  check. CI repeats all of it, plus the tests, the build, the end-to-end journey, and a
  dependency audit.

Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`,
`docs:`, `chore:`).

## Adding a new data source

Adding an eleventh source never requires editing the code that runs the existing ten.

1. Write a class with a `source_id`, a `source_name`, and an `ingest` method, in
   `backend/src/shadow_cpi/ingestion/official/` for a source with an API, or add an
   entry to `SCRAPED_SOURCES` in `.../ingestion/brightdata/collectors.py` for one that
   has to be read from a page.
2. Declare a pydantic model for the raw payload, so the source validates its own input
   before normalization.
3. Register it with `@default_registry.source("your_source_id")`. The scheduler and the
   API discover it from there; neither file changes.
4. Write the tests first: a healthy payload, a malformed payload, and for scraped
   sources the path where the page changed and the collector repairs itself.

A scraped source needs no new code at all. `ScrapedSource` describes the page, the
values to extract, and how to store them, and one shared implementation runs it.
