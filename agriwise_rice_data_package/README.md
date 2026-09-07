# AgriWise Karnataka Rice Price Data Package

This package pulls Karnataka **Rice** mandi price records from the Government of India's Open Government Data (OGD) / AGMARKNET resource and converts them into a clean CSV suitable for the AgriWise price-prediction pipeline.

## What it does

1. Calls the AGMARKNET dataset through `api.data.gov.in`.
2. Filters to `State = Karnataka` and `Commodity = Rice`.
3. Paginates through the API without generating or imputing prices.
4. Saves a raw CSV for auditability.
5. Cleans dates/prices, removes invalid/duplicate rows, and preserves market/variety/grade.
6. Writes the final file to `data/clean/karnataka_rice_prices.csv`.

## Sources

Primary: Government of India, Directorate of Marketing & Inspection (DMI), Ministry of Agriculture and Farmers Welfare, OGD/AGMARKNET.

Current daily resource: `9ef84268-d588-465a-a308-a864a43d0070`

Historical resource used by this package: `35985678-0d79-46b4-9ed6-6f13308a1d24`.

Secondary cross-check/source option: CEDA Agri Market Data, which states its Agri-Market Data are sourced from DMI/Ministry of Agriculture and provides a programmatic API.

## Windows setup

Open PowerShell in this package folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Then put your real data.gov.in API key into `.env`:

```text
DATA_GOV_API_KEY=YOUR_REAL_KEY
```

Get the key from https://data.gov.in/ . Do not commit `.env` or publish the key.

## Run the full extraction

```powershell
python scripts/run_pipeline.py
```

Final output:

```text
data/clean/karnataka_rice_prices.csv
```

Raw audit copy:

```text
data/raw/karnataka_rice_agmarknet_raw.csv
```

Metadata:

```text
data/raw/karnataka_rice_agmarknet_raw.meta.json
```

## Build a historical window

You can locally constrain the cleaned output:

```powershell
python scripts/run_pipeline.py --start-date 2018-01-01 --max-date 2026-09-01
```

For a very large Karnataka history, let the API pagination complete first; the script is intentionally conservative about request pacing.

## Targeted exact-date pull

The fetcher supports an exact AGMARKNET arrival-date filter:

```powershell
python scripts/fetch_rice_karnataka.py --start-date 05/09/2026 --output data/raw/rice_2026-09-05.csv
```

This is useful for daily updates.

## Integrating with your AgriWise project

Assuming your current project is:

```text
CropMandi-AI-main/
```

copy these package pieces into your project:

```text
services/rice_data_api.py -> CropMandi-AI-main/services/rice_data_api.py
scripts/fetch_rice_karnataka.py -> CropMandi-AI-main/scripts/fetch_rice_karnataka.py
scripts/clean_rice_data.py -> CropMandi-AI-main/scripts/clean_rice_data.py
scripts/run_pipeline.py -> CropMandi-AI-main/scripts/run_rice_pipeline.py
```

Then put the final CSV here:

```text
datasets/karnataka_rice_prices.csv
```

For your existing model, preserve these columns:

```text
state
 district
 market
 commodity
 variety
 grade
 arrival_date
 min_price
 max_price
 modal_price
```

Your current prediction system primarily models `modal_price`; min/max are retained as useful source fields.

## Recommended model workflow

```text
AGMARKNET
   -> raw CSV
   -> cleaning
   -> datasets/karnataka_rice_prices.csv
   -> PriceRepository / training script
   -> feature engineering
   -> Random Forest
   -> saved model
   -> Flask prediction API
   -> dashboard
```

Do NOT pool all varieties into one anonymous series. The current AgriWise model already has categorical inputs such as market, commodity and variety, so retaining those dimensions is important.

## Daily updates

For a scheduled daily update, run:

```powershell
python scripts/fetch_rice_karnataka.py --start-date DD/MM/YYYY --output data/raw/today_rice.csv
```

Then clean/merge into your main dataset. A simpler production approach is to run the full Karnataka Rice pull on a schedule, deduplicate on:

```text
state + district + market + commodity + variety + grade + arrival_date
```

and append only new dates.

## CEDA optional fallback

CEDA provides an Agmarknet API and reports broad historical coverage. It requires registering for an API key. The CEDA API documentation is available at:

https://api.ceda.ashoka.edu.in/documentation/

This package keeps CEDA as an optional secondary source rather than silently mixing two feeds into the same training table. That keeps provenance clear.

## Important data-quality rules

- Prices are kept in Rs./quintal, the unit used by AGMARKNET.
- Rows with missing/zero modal price are removed from the ML-ready CSV.
- Min/modal/max ordering is checked when all three are present.
- No synthetic values are generated.
- No missing price values are filled by guessing.
- Rice and Paddy are kept separate.

## Verification

The official OGD dataset page identifies the dataset as daily-granularity mandi prices and identifies DMI under the Ministry of Agriculture and Farmers Welfare as the source. AGMARKNET's operating documentation describes market-level variety-wise minimum, maximum and modal prices in Rs./quintal.

## Merge multiple pulls

If you make several dated pulls, merge them without double-counting:

```powershell
python scripts/merge_rice_data.py --input data/clean/karnataka_rice_prices.csv --input data/raw/today_rice.csv
```

Then validate:

```powershell
python scripts/verify_rice_dataset.py
```

## Hooking into the existing AgriWise training script

Your existing model expects the same conceptual fields already used for coffee/other commodities. The safest integration is:

```text
package output
   -> datasets/karnataka_rice_prices.csv
   -> your existing training script
   -> filter commodity == Rice
   -> create lags/rolling features per market+variety series
   -> train Random Forest
   -> save models/price_prediction_model.joblib
```

If your current `train_price_model.py` reads one combined dataset, append the clean Rice CSV to that combined dataset and keep `commodity=Rice`. Do not overwrite the existing coffee/cardamom/pepper records.

## Daily production update pattern

For production, prefer incremental daily pulls rather than downloading years of history on every request:

```text
Daily scheduler
     |
     v
fetch_rice_karnataka.py
     |
     v
raw/today_rice.csv
     |
     v
merge_rice_data.py
     |
     v
datasets/karnataka_rice_prices.csv
     |
     v
retrain/refresh model (scheduled separately)
```

Run the downloader outside the Flask request path so a slow government API does not block farmers using the web app.
