# AgriWise AI - Cold Storage Package

## Contents

- `services/storage_service.py`
  - Drop into the friend's `services/` directory.
  - Implements `find_nearby_storages(...)`.
  - Uses OpenRouteService when `ORS_API_KEY` is configured.
  - Falls back to explicitly-labelled straight-line distance when routing is unavailable.
  - Supports geocoding for records missing coordinates.

- `data/nhb_karnataka_cold_storages.csv`
  - Karnataka cold-storage project records extracted from an NHB-published Karnataka CISS document.
  - Source: https://nhb.gov.in/doc/karnataka.pdf
  - These are NHB project/sanction records, not a guarantee that every listed unit is operating today.
  - For current operational/open-now verification, run the status checker.

- `data/demo_project_cold_storages.csv`
  - Four coordinates already used by the AgriWise project for the Mysuru cold-storage demo.
  - These are marked as project-dataset records, not NHB source records.

- `scripts/check_cold_storage_status.py`
  - Verifies operational/open-now status through Google Places API (New).
  - Requires `GOOGLE_MAPS_API_KEY`.
  - Produces `operational_status`, `open_now`, Google place ID and Maps URL.
  - `unknown` is returned when there is no confident match; the script never guesses.

- `scripts/import_project_data.py`
  - Generic Firebase/Firestore importer for CSV, JSON and JSONL files.
  - Uses your existing Firebase service-account environment configuration.
  - Deterministic document IDs make reruns idempotent.

## Installation

In the project:

```powershell
pip install requests python-dotenv
```

If Firebase Admin is not already installed:

```powershell
pip install firebase-admin
```

## Environment

`.env`:

```text
FIREBASE_SERVICE_ACCOUNT_JSON=firebase-service-account.json
ORS_API_KEY=YOUR_ORS_KEY
GOOGLE_MAPS_API_KEY=YOUR_GOOGLE_PLACES_KEY
COLD_STORAGE_ENABLE_GEOCODING=true
```

Do NOT commit service-account JSON or API keys to Git.

## Installing the cold-storage feature

Copy:

```text
services/storage_service.py
```

into:

```text
<friend-project>/services/storage_service.py
```

Copy:

```text
data/nhb_karnataka_cold_storages.csv
data/demo_project_cold_storages.csv
```

into:

```text
<friend-project>/datasets/
```

The service automatically attempts to load `datasets/cold_storages.csv` plus the two package datasets.

The API already expected:

```python
storage_service.find_nearby_storages(
    latitude=latitude,
    longitude=longitude,
    crop=crop,
    quantity_kg=quantity_kg,
    district=district,
    max_distance_km=max_distance,
    limit=limit,
)
```

## Verify status

```powershell
python scripts/check_cold_storage_status.py `
  --csv datasets/nhb_karnataka_cold_storages.csv `
  --output datasets/nhb_karnataka_cold_storages_status.csv
```

Google Places uses business status plus current opening hours; "operational" does not automatically mean "open right now".

## Import all of her data into your Firebase project

Put her CSV/JSON files into:

```text
incoming_data/
```

Then run:

```powershell
python scripts/import_project_data.py --data-dir incoming_data
```

Or force a particular collection:

```powershell
python scripts/import_project_data.py `
  --data-dir incoming_data `
  --collection her_data
```

The script prints the collection and number of upserts for every file.

## Important integration note

The existing AgriWise `/api/cold-storages` endpoint calls `StorageService.find_nearby_storages(...)` and expects storage records with distance/ETA information.

The current frontend also calls:

```text
/api/cold-storages?latitude=...&longitude=...
```

and renders `storages` returned by the endpoint.

This package therefore matches the existing application contract instead of introducing a second cold-storage API.
