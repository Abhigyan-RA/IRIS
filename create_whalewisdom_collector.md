# Creating WhaleWisdom Bright Data Collector

To complete the WhaleWisdom data collection setup, you need to create a Bright Data Scraper Studio collector.

## Step 1: Install Bright Data CLI

```bash
npm install -g @brightdata/cli
```

## Step 2: Create the WhaleWisdom Collector

Run this command to create a collector for WhaleWisdom fund holdings:

```bash
npx -p @brightdata/cli bdata scraper create \
  "https://whalewisdom.com/filer/bridgewater-associates-lp#tabholdings_tab" \
  "Extract institutional fund holdings data: fund name, stock ticker symbol, shares held, market value in USD, percent of portfolio, quarterly change in shares, and stock name"
```

## Step 3: Update Configuration

The command will output a collector ID like `c_abc123xyz`. Update your `.env` file:

```
SCRAPER_STUDIO_COLLECTORS=lme_copper_scraper=c_mswnopw72dyj64c7s3,baltic_dry_scraper=c_msxf7dmsk2nlv2jce,oilprice_scraper=c_msxfckpn1d2xsb97bb,fbx_scraper=c_msy17cdnvqtmi85ej,whalewisdom_13f_scraper=c_YOUR_ACTUAL_COLLECTOR_ID
```

## Step 4: Test Collection

After creating the collector, test it:

```bash
# Test WhaleWisdom scraper specifically
backend\.venv\Scripts\python -m shadow_cpi.collect --source whalewisdom_13f_scraper

# Test SEC EDGAR with expanded fund list
backend\.venv\Scripts\python -m shadow_cpi.collect --source sec_edgar_13f

# Collect from all sources
backend\.venv\Scripts\python -m shadow_cpi.collect
```

## Expected Results

With the expanded configuration:

- **SEC EDGAR**: Should collect from ~20 major funds = thousands of holdings
- **WhaleWisdom**: Should collect enrichment data for the same funds
- **Total data**: 20+ funds × ~100-1000 holdings each = 10,000+ records

## Troubleshooting

If you get "not configured" errors:

1. Verify your Bright Data API key is set: `BRIGHTDATA_API_KEY`
2. Ensure the collector ID is correctly added to `SCRAPER_STUDIO_COLLECTORS`
3. Check the collector was created successfully in Bright Data dashboard

## Monitoring Collection

Check collection health:

```bash
backend\.venv\Scripts\python -m shadow_cpi.collect --list
```

Monitor the dashboard pipeline health section to see collection status and any errors.
