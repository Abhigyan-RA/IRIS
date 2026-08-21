"""Manual import script for WhaleWisdom data collected via CLI.

Usage:
1. Run the collector via CLI and save output to a file:
   npx @brightdata/cli scraper run c_mt1n3f5x457bnke4f "URL" --json > bridgewater.json

2. Run this script to import the data:
   python import_whalewisdom_data.py bridgewater.json 0001350694 "Bridgewater Associates"
"""

import sys
import json
from pathlib import Path
from datetime import UTC, date, datetime

# Add the backend source to path
sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))

from shadow_cpi.shared import InstitutionalFundSnapshot, InstitutionalHoldingEnrichment
from shadow_cpi.config import get_settings
from shadow_cpi.db.timescale.executor import PsycopgExecutor
from psycopg_pool import AsyncConnectionPool
import asyncio

# Load .env from the repo root (two levels up from backend/src)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")


async def import_data(json_file: str, cik: str, fund_name: str, slug: str):
    """Import WhaleWisdom data from a JSON file."""
    
    # Read the JSON file
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    if not isinstance(data, list) or len(data) == 0:
        print(f"No data found in {json_file}")
        return
    
    row = data[0]  # First row contains the holdings
    holdings_data = row.get('holdings', [])
    
    if not holdings_data:
        print(f"No holdings found in {json_file}")
        return
    
    # Create snapshot and enrichments
    quarter = date(2026, 6, 30)  # Q2 2026
    observed_at = datetime.now(UTC)
    url = f"https://whalewisdom.com/filer/{slug}"
    
    # Calculate total value
    total_value = sum(h.get('market_value', 0) for h in holdings_data)
    
    snapshot = InstitutionalFundSnapshot(
        filer_name=fund_name,
        filer_cik=cik,
        report_period=quarter,
        reported_value_usd=total_value,
        holdings_count=len(holdings_data),
        source_url=url,
        observed_at=observed_at,
    )
    
    enrichments = []
    for rank, item in enumerate(holdings_data, start=1):
        ticker = item.get('ticker', '').strip().upper()
        if not ticker:
            continue
        
        # Parse change_in_shares
        change_str = str(item.get('change_in_shares', '')).replace(',', '').strip()
        try:
            change = float(change_str) if change_str and change_str not in ['new', 'N/A', '--'] else None
        except:
            change = None
        
        enrichments.append(
            InstitutionalHoldingEnrichment(
                filer_cik=cik,
                stock_ticker=ticker,
                quarter_end=quarter,
                stock_name=None,
                sector=item.get('sector'),
                rank=rank,
                reported_pct_change_shares=change,
                source_url=url,
                observed_at=observed_at,
            )
        )
    
    # Store in database
    settings = get_settings()
    async with AsyncConnectionPool(settings.database_url, open=False) as pool:
        await pool.open(wait=True)
        from typing import cast
        from shadow_cpi.db.timescale.executor import ConnectionPool
        
        executor = PsycopgExecutor(cast("ConnectionPool", pool))
        
        # Insert snapshot
        await executor.execute("""
            INSERT INTO institutional_fund_snapshots 
            (filer_name, filer_cik, report_period, reported_value_usd, holdings_count,
             source_name, source_url, ingestion_method, observed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (filer_cik, report_period) DO UPDATE
            SET reported_value_usd = EXCLUDED.reported_value_usd,
                holdings_count = EXCLUDED.holdings_count,
                observed_at = EXCLUDED.observed_at
        """, [snapshot.filer_name, snapshot.filer_cik, snapshot.report_period,
            snapshot.reported_value_usd, snapshot.holdings_count,
            'whalewisdom', snapshot.source_url, 'brightdata_scrape', snapshot.observed_at])
        
        # Insert enrichments
        for enr in enrichments:
            await executor.execute("""
                INSERT INTO institutional_holding_enrichments
                (filer_cik, stock_ticker, quarter_end, stock_name, sector, rank,
                 reported_pct_change_shares, source_name, source_url, ingestion_method, observed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (filer_cik, stock_ticker, quarter_end) DO UPDATE
                SET stock_name = EXCLUDED.stock_name,
                    sector = EXCLUDED.sector,
                    rank = EXCLUDED.rank,
                    reported_pct_change_shares = EXCLUDED.reported_pct_change_shares,
                    observed_at = EXCLUDED.observed_at
            """, [enr.filer_cik, enr.stock_ticker, enr.quarter_end, enr.stock_name,
                enr.sector, enr.rank, enr.reported_pct_change_shares,
                'whalewisdom', enr.source_url, 'brightdata_scrape', enr.observed_at])
    
    print(f"[ok] Imported {fund_name}: {len(enrichments)} holdings, ${total_value:,.0f} total value")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    
    json_file = sys.argv[1]
    cik = sys.argv[2]
    fund_name = sys.argv[3]
    slug = sys.argv[4] if len(sys.argv) > 4 else fund_name.lower().replace(' ', '-')
    
    # psycopg requires SelectorEventLoop on Windows (ProactorEventLoop is the default)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(import_data(json_file, cik, fund_name, slug))
