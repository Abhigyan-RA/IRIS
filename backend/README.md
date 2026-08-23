# Backend

The FastAPI service behind Shadow CPI. It collects data from public sources,
normalizes it into one shape, stores it, and serves it through a REST API and an
MCP server.

Setup instructions live in the [repository README](../README.md).

## Where things live

| Path                                      | What it does                                                                          |
| ----------------------------------------- | ------------------------------------------------------------------------------------- |
| `src/shadow_cpi/config.py`                | Reads and validates every environment variable. Nothing else touches the environment. |
| `src/shadow_cpi/shared/`                  | Data schemas and domain types shared across packages.                                 |
| `src/shadow_cpi/db/`                      | Database migrations and the classes that read and write data.                         |
| `src/shadow_cpi/db/timescale/migrations/` | Numbered SQL files that define the schema. Add a file to change it.                   |
| `src/shadow_cpi/db/prepare.py`            | One command: apply migrations, create graph constraints, load the starting graph.     |
| `src/shadow_cpi/db/smoke_check.py`        | Writes and reads real rows against live databases, then removes them again.           |
| `src/shadow_cpi/runtime.py`               | Event loop selection, which must happen before any async work starts.                 |
| `src/shadow_cpi/ingestion/`               | One module per data source: official API clients and scrapers.                        |
| `src/shadow_cpi/ai/`                      | The Gemini client and the prompt templates it uses.                                   |
| `src/shadow_cpi/api/`                     | HTTP routes, middleware, and the server entrypoint.                                   |
| `src/shadow_cpi/mcp_server/`              | Tools exposed to AI agents and IDEs.                                                  |
| `src/shadow_cpi/tooling/`                 | Repository checks used by the pre-commit hook and CI.                                 |
| `tests/`                                  | Test suite, mirroring the layout above.                                               |

Packages appear as the corresponding build phase lands.

## Design rules

These are the conventions the code follows; keeping to them is what keeps the
service easy to change.

- **One job per class.** An ingestor fetches from one source. The normalizer only
  normalizes. A repository only reads or writes.
- **Adding a source does not mean editing existing code.** Every source
  implements the same interface and registers itself; the scheduler discovers it.
- **Dependencies are passed in, not imported.** Services receive a database
  client or HTTP client at construction time. That is what makes it possible to
  test them without a real database or network call.
- **Validate at the boundary.** Anything arriving from outside (an API response,
  a scraped page, a request body) is validated against a schema before any other
  code sees it. Invalid data is rejected, not patched up.
- **Parameterized queries only**, for both SQL and Cypher. No string building.

## Commands

Paths below use the Windows virtualenv layout; on macOS and Linux replace
`.venv/Scripts/` with `.venv/bin/`.

```bash
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"     # install
.venv/Scripts/python -m pytest                                    # run tests
.venv/Scripts/python -m pytest --cov --cov-report=term-missing     # coverage
.venv/Scripts/python -m ruff check .                               # lint
.venv/Scripts/python -m ruff format .                              # format
.venv/Scripts/python -m mypy                                       # type check
.venv/Scripts/python -m shadow_cpi.api.main                        # run the API
```

The test suite fails if coverage drops below 80 percent, and also fails if any
test is skipped: a skipped test hides a gap behind a green build.
