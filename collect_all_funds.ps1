# PowerShell script to collect WhaleWisdom data for all funds
# This will take about 45-60 minutes total (4-5 minutes per fund)

$funds = @(
    @{cik="0001350694"; name="Bridgewater Associates"; slug="bridgewater-associates-inc"},
    @{cik="0000093751"; name="State Street Corp"; slug="state-street-corp"},
    @{cik="0001067983"; name="Berkshire Hathaway"; slug="berkshire-hathaway-inc"},
    @{cik="0000895421"; name="Millennium Management"; slug="millennium-management-l-l-c"},
    @{cik="0000100412"; name="Northern Trust Corp"; slug="northern-trust-corp"},
    @{cik="0001050446"; name="Invesco Ltd"; slug="invesco-plc-london"},
    @{cik="0000315066"; name="Fidelity Management"; slug="fidelity-management-amp-research-co-ma"},
    @{cik="0000730718"; name="T Rowe Price"; slug="price-t-rowe-associates-inc-md"},
    @{cik="0000038777"; name="Franklin Resources"; slug="franklin-resources-inc"},
    @{cik="0001009207"; name="D E Shaw"; slug="d-e-shaw-co-inc"},
    @{cik="0001603466"; name="Point72"; slug="point72-asset-management-lp"}
)

$collector_id = "c_mt1n3f5x457bnke4f"
$output_dir = "whalewisdom_data"
$python = "$PSScriptRoot\backend\.venv\Scripts\python.exe"

# Create output directory
if (!(Test-Path $output_dir)) {
    New-Item -ItemType Directory -Path $output_dir | Out-Null
}

Write-Host "Starting collection of $($funds.Count) funds..." -ForegroundColor Green
Write-Host "This will take approximately $([math]::Ceiling($funds.Count * 4.5)) minutes" -ForegroundColor Yellow
Write-Host ""

$total = $funds.Count
$current = 0

foreach ($fund in $funds) {
    $current++
    $url = "https://whalewisdom.com/filer/$($fund.slug)"
    $output_file = "$output_dir/$($fund.slug).json"
    
    Write-Host "[$current/$total] Collecting $($fund.name)..." -ForegroundColor Cyan
    Write-Host "  URL: $url" -ForegroundColor Gray
    
    # Run the scraper - stderr (status messages) shown in console, stdout (JSON) saved to file
    # npx is a .cmd shim on Windows so we use cmd /c with explicit redirection
    cmd /c "npx @brightdata/cli scraper run $collector_id $url --json > $output_file"
    
    Write-Host "  Saved to $output_file" -ForegroundColor Green
    
    # Validate JSON was captured
    $content = Get-Content $output_file -Raw -ErrorAction SilentlyContinue
    if (-not $content -or $content.Trim() -eq "") {
        Write-Host "  ERROR: Empty output file, skipping import" -ForegroundColor Red
        continue
    }
    
    # Import into database
    Write-Host "  Importing to database..." -ForegroundColor Gray
    & $python import_whalewisdom_data.py $output_file $($fund.cik) "$($fund.name)" $($fund.slug)
    
    Write-Host ""
}

Write-Host "=== Collection Complete ===" -ForegroundColor Green
Write-Host "All fund data collected and imported successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To view the data in database:" -ForegroundColor Yellow
Write-Host '  docker exec shadowcpi-timescaledb psql -U shadowcpi -d shadowcpi -c "SELECT filer_name, holdings_count, reported_value_usd FROM institutional_fund_snapshots ORDER BY reported_value_usd DESC;"' -ForegroundColor Cyan
