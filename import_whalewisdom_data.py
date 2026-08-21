"""Load WhaleWisdom pages that were already collected to files.

The collector normally writes straight to the database. This replays payloads that
were saved earlier, which is useful when a page was collected by hand or when a long
collection run should not be repeated.

It reuses the collector's own parser and the configured watchlist, so a replayed page
is stored exactly as a live collection would store it. Nothing here maps fields on its
own: a second mapping would be free to disagree with the first.

Usage, from the repository root:

    # every file in a directory, matched to the watchlist by page slug
    backend/.venv/Scripts/python import_whalewisdom_data.py whalewisdom_data

    # one file, naming the fund page it came from
    backend/.venv/Scripts/python import_whalewisdom_data.py file.json --slug state-street-corp

A file whose slug is not on the watchlist is reported and skipped, because storing it
would attach holdings to a fund the official ingestor does not track.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))

from shadow_cpi.db.timescale.executor import ConnectionPool, PsycopgExecutor
from shadow_cpi.db.timescale.repositories import TimescaleHoldingsRepository
from shadow_cpi.ingestion.brightdata.whalewisdom import (
    DEFAULT_WHALEWISDOM_FUNDS,
    WhaleWisdomFund,
    _parse_result,
)
from shadow_cpi.runtime import bootstrap


def _watchlist() -> dict[str, WhaleWisdomFund]:
    """Return the configured funds, keyed by the page slug they are collected from."""
    return {fund.slug: fund for fund in DEFAULT_WHALEWISDOM_FUNDS}


def _rows_of(path: Path) -> list[dict[str, object]]:
    """Read one saved collector payload.

    Args:
        path: File holding the JSON the collector returned.

    Returns:
        The result objects it contains.
    """
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    # A CLI run can print progress around the payload, so the array is located rather
    # than assumed to start at the first character.
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    decoded = json.loads(text[start : end + 1])
    return [row for row in decoded if isinstance(row, dict)]


async def _store(
    files: list[tuple[Path, WhaleWisdomFund]],
    quarter: date | None,
) -> int:
    """Parse and store every file, reporting one line per fund.

    Args:
        files: Saved payloads paired with the fund whose page they came from.
        quarter: Quarter the operator states these pages describe, used only for a
            payload that does not carry its own. Nothing is inferred when it is absent.

    Returns:
        Process exit status: zero when at least one fund was stored.
    """
    from psycopg_pool import AsyncConnectionPool

    from shadow_cpi.config import get_settings

    observed_at = datetime.now(UTC)
    settings = get_settings()
    stored = 0

    async with AsyncConnectionPool(settings.database_url, open=False) as pool:
        await pool.open(wait=True)
        repository = TimescaleHoldingsRepository(
            PsycopgExecutor(cast("ConnectionPool", pool)),
        )

        for path, fund in files:
            rows = _rows_of(path)
            if not rows:
                sys.stdout.write(f"[skip] {fund.name}: no payload in {path.name}\n")
                continue

            snapshots = []
            enrichments = []
            for row in rows:
                # A page that states its own quarter always wins. The stated quarter is
                # only supplied when the payload carries none, so the parser stays the
                # single place that decides what a page means.
                if quarter is not None and not row.get("quarter"):
                    row = {**row, "quarter": quarter.isoformat()}
                parsed = _parse_result(row, fund, observed_at)
                if parsed is None:
                    continue
                snapshot, holding_rows = parsed
                snapshots.append(snapshot)
                enrichments.extend(holding_rows)

            if not snapshots:
                sys.stdout.write(
                    f"[skip] {fund.name}: page states no quarter or no holdings"
                    f"{'' if quarter else '; pass --quarter to state it'}\n",
                )
                continue

            await repository.upsert_fund_snapshots(snapshots)
            await repository.upsert_holding_enrichments(enrichments)
            stored += 1
            sys.stdout.write(
                f"[ok]   {fund.name} ({fund.cik}): "
                f"{len(enrichments)} holdings from {path.name}\n",
            )

    sys.stdout.write(f"\n{stored} of {len(files)} funds stored\n")
    return 0 if stored else 1


def main() -> int:
    """Match saved payloads to the watchlist and store them.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="a saved payload, or a directory of them")
    parser.add_argument(
        "--slug",
        help="page slug the file came from, when it cannot be read from the file name",
    )
    parser.add_argument(
        "--quarter",
        type=date.fromisoformat,
        help=(
            "quarter these pages describe, as YYYY-MM-DD, for payloads that do not state "
            "one themselves. A payload that states its own quarter is unaffected."
        ),
    )
    args = parser.parse_args()

    watchlist = _watchlist()
    candidates = (
        sorted(args.path.glob("*.json")) if args.path.is_dir() else [cast("Path", args.path)]
    )
    if not candidates:
        sys.stderr.write(f"No JSON payloads found in {args.path}\n")
        return 1

    files: list[tuple[Path, WhaleWisdomFund]] = []
    for path in candidates:
        slug = args.slug or path.stem
        fund = watchlist.get(slug)
        if fund is None:
            sys.stderr.write(
                f"[skip] {path.name}: '{slug}' is not on the configured watchlist, so it "
                f"has no tracked fund to attach to\n",
            )
            continue
        files.append((path, fund))

    if not files:
        sys.stderr.write("Nothing to store: no file matched the configured watchlist\n")
        return 1

    # psycopg needs the selector loop on Windows; the default proactor loop cannot run it.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    return asyncio.run(_store(files, args.quarter))


if __name__ == "__main__":
    bootstrap()
    raise SystemExit(main())
