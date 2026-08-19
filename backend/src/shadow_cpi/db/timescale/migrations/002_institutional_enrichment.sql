-- WhaleWisdom enriches the official SEC holdings without replacing them.
--
-- The SEC table remains the authoritative ledger for shares and values. These tables hold
-- only human-readable and proprietary fields from a commercial public page. Keeping that
-- boundary in the schema means a broken scraper cannot overwrite a regulator-sourced row.

CREATE TABLE IF NOT EXISTS institutional_fund_snapshots (
    id                         UUID          NOT NULL DEFAULT gen_random_uuid(),
    filer_name                 VARCHAR(255)  NOT NULL,
    filer_cik                  VARCHAR(20)   NOT NULL,
    report_period              DATE          NOT NULL,
    filing_date                DATE,
    reported_value_usd         DECIMAL(18,2),
    discretionary_aum_usd      DECIMAL(18,2),
    top_10_concentration_pct   DECIMAL(6,3),
    holdings_count             INTEGER,
    portfolio_turnover_pct     DECIMAL(12,3),
    whale_score                DECIMAL(12,3),
    source_name                VARCHAR(100)  NOT NULL,
    source_url                 TEXT          NOT NULL,
    ingestion_method           VARCHAR(30)   NOT NULL,
    observed_at                TIMESTAMPTZ   NOT NULL,
    CONSTRAINT unique_fund_snapshot UNIQUE (filer_cik, report_period)
);

CREATE INDEX IF NOT EXISTS idx_fund_snapshots_period
    ON institutional_fund_snapshots (report_period DESC, filer_cik);

CREATE TABLE IF NOT EXISTS institutional_holding_enrichments (
    id                           UUID          NOT NULL DEFAULT gen_random_uuid(),
    filer_cik                    VARCHAR(20)   NOT NULL,
    stock_ticker                 VARCHAR(10)   NOT NULL,
    quarter_end                  DATE          NOT NULL,
    stock_name                   VARCHAR(255),
    previous_pct_portfolio       DECIMAL(6,3),
    rank                         INTEGER,
    reported_pct_change_shares   DECIMAL(12,3),
    quarter_first_owned          VARCHAR(30),
    estimated_avg_price          DECIMAL(18,4),
    source_name                  VARCHAR(100)  NOT NULL,
    source_url                   TEXT          NOT NULL,
    ingestion_method             VARCHAR(30)   NOT NULL,
    observed_at                  TIMESTAMPTZ   NOT NULL,
    CONSTRAINT unique_holding_enrichment UNIQUE (filer_cik, stock_ticker, quarter_end)
);

CREATE INDEX IF NOT EXISTS idx_holding_enrichments_ticker_quarter
    ON institutional_holding_enrichments (stock_ticker, quarter_end DESC);

CREATE INDEX IF NOT EXISTS idx_holding_enrichments_filer_quarter
    ON institutional_holding_enrichments (filer_cik, quarter_end DESC);
