-- Initial schema: price history, institutional holdings, and pipeline events.
--
-- All three tables are TimescaleDB hypertables. A hypertable looks and behaves
-- like a normal PostgreSQL table, but is stored as many time-based chunks, which
-- keeps "the last 30 days for this entity" fast as history grows.
--
-- Each table is partitioned by the time column that queries actually filter on:
-- prices by observation time, holdings by the quarter they describe, and events
-- by when they happened. TimescaleDB requires any unique index to include the
-- partitioning column, which is why the natural keys below all contain a time
-- column.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Needed for gen_random_uuid() on PostgreSQL versions where it is not built in.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- commodity_prices: one observed price for one thing at one moment.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS commodity_prices (
    id                UUID          NOT NULL DEFAULT gen_random_uuid(),
    entity_name       VARCHAR(255)  NOT NULL,  -- Copper, Steel_HRC_US, FBX01
    sector            VARCHAR(50)   NOT NULL,  -- freight, energy, metals, agriculture
    price             DECIMAL(14,4) NOT NULL,  -- may be negative: oil has traded below zero
    currency          VARCHAR(3)    NOT NULL,  -- ISO 4217 code
    unit              VARCHAR(50)   NOT NULL,  -- barrel, metric_ton, feu, index_point, lb
    pct_change_1d     DECIMAL(6,3),
    pct_change_7d     DECIMAL(6,3),
    recorded_at       TIMESTAMPTZ   NOT NULL,
    source_name       VARCHAR(100)  NOT NULL,
    source_url        TEXT          NOT NULL,  -- every number is traceable to its origin
    ingestion_method  VARCHAR(20)   NOT NULL,  -- official_api or brightdata_scrape
    -- One price per entity per timestamp. Re-running a collector updates the
    -- existing row instead of creating a duplicate.
    CONSTRAINT unique_daily_price UNIQUE (entity_name, recorded_at)
);

SELECT create_hypertable('commodity_prices', 'recorded_at', if_not_exists => TRUE);

-- Supports the trend chart: recent history for one entity.
CREATE INDEX IF NOT EXISTS idx_prices_entity_time
    ON commodity_prices (entity_name, recorded_at DESC);

-- Supports the risk map: what moved most recently across a sector.
CREATE INDEX IF NOT EXISTS idx_prices_sector_time
    ON commodity_prices (sector, recorded_at DESC);

-- ---------------------------------------------------------------------------
-- institutional_holdings: one position from one quarterly disclosure.
--
-- Partitioned by quarter_end rather than recorded_at, because the quarter is
-- what queries filter on and what makes a position unique. recorded_at is kept
-- as an audit trail of when we read the filing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS institutional_holdings (
    id                 UUID           NOT NULL DEFAULT gen_random_uuid(),
    filer_name         VARCHAR(255)   NOT NULL,  -- Bridgewater Associates
    filer_cik          VARCHAR(20)    NOT NULL,  -- ten digits, zero padded
    stock_ticker       VARCHAR(10)    NOT NULL,
    shares_held        BIGINT         NOT NULL,
    market_value_usd   DECIMAL(18,2),
    pct_portfolio      DECIMAL(6,3),
    shares_change_qoq  BIGINT,
    quarter_end        DATE           NOT NULL,
    source_url         TEXT,
    recorded_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    -- One row per filer, per stock, per quarter.
    CONSTRAINT unique_filer_stock_quarter UNIQUE (filer_cik, stock_ticker, quarter_end)
);

SELECT create_hypertable('institutional_holdings', 'quarter_end', if_not_exists => TRUE);

-- Supports "which funds hold this stock".
CREATE INDEX IF NOT EXISTS idx_holdings_ticker_quarter
    ON institutional_holdings (stock_ticker, quarter_end DESC);

-- Supports "what does this fund hold".
CREATE INDEX IF NOT EXISTS idx_holdings_filer_quarter
    ON institutional_holdings (filer_cik, quarter_end DESC);

-- ---------------------------------------------------------------------------
-- pipeline_health_events: the audit trail behind the health feed.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_health_events (
    id           UUID         NOT NULL DEFAULT gen_random_uuid(),
    scraper_id   VARCHAR(100) NOT NULL,
    source_name  VARCHAR(100) NOT NULL,
    event_type   VARCHAR(30)  NOT NULL,  -- success, dom_shift_detected,
                                         -- self_heal_triggered, self_heal_resolved,
                                         -- self_heal_failed
    message      TEXT,
    occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

SELECT create_hypertable('pipeline_health_events', 'occurred_at', if_not_exists => TRUE);

-- Supports the live feed: newest events, optionally filtered to one collector.
CREATE INDEX IF NOT EXISTS idx_events_scraper_time
    ON pipeline_health_events (scraper_id, occurred_at DESC);
