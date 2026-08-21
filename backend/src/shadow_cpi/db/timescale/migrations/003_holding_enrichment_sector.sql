-- Migration 003: add sector column to institutional_holding_enrichments
--
-- WhaleWisdom returns a GICS sector string per holding (e.g. "INFORMATION TECHNOLOGY").
-- Previously this was incorrectly stored in stock_name. This migration adds a proper
-- sector column and clears the misplaced values from stock_name.

ALTER TABLE institutional_holding_enrichments
    ADD COLUMN IF NOT EXISTS sector VARCHAR(100);

-- Clear the sector strings that were incorrectly stored in stock_name.
-- stock_name should hold a company name; the values currently there are sector
-- labels like "FINANCE" or "INFORMATION TECHNOLOGY" from the WhaleWisdom scraper.
UPDATE institutional_holding_enrichments
SET
    sector = stock_name,
    stock_name = NULL
WHERE ingestion_method = 'brightdata_scrape'
  AND stock_name IS NOT NULL
  AND stock_name = UPPER(stock_name);  -- sector labels are all-caps; real names are not
