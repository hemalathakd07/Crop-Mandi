"""Fetch Karnataka Rice mandi prices from the Government OGD/AGMARKNET API.

Outputs a raw CSV without inventing or imputing prices.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.rice_data_api import get_client


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().replace("_x0020_", " ") for c in df.columns]
    # Preserve original fields and add predictable lowercase aliases.
    alias = {}
    for c in df.columns:
        key = c.strip().lower().replace(" ", "_")
        alias[c] = key
    df = df.rename(columns=alias)
    return df


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", help="Optional DD/MM/YYYY exact arrival-date filter")
    parser.add_argument("--end-date", help="Optional local post-filter upper bound YYYY-MM-DD")
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--output", default="data/raw/karnataka_rice_agmarknet_raw.csv")
    parser.add_argument("--resource-id", default=os.getenv(
        "DATA_GOV_HISTORICAL_RESOURCE_ID", "35985678-0d79-46b4-9ed6-6f13308a1d24"))
    args = parser.parse_args()

    client = get_client(args.resource_id)
    filters = {"State": "Karnataka", "Commodity": "Rice"}
    if args.start_date:
        # Exact-date filtering is supported by OGD deployments and is useful for targeted pulls.
        # For broad historical ranges we intentionally fetch the state+commodity panel and filter locally.
        filters["Arrival_Date"] = args.start_date

    records = client.fetch_all(filters=filters, max_rows=args.max_rows)
    if not records:
        raise SystemExit("No records returned. Check API key/resource availability/filters.")

    df = clean_columns(pd.DataFrame(records))
    if "state" in df.columns:
        df = df[df["state"].astype(str).str.strip().str.casefold() == "karnataka"]
    if "commodity" in df.columns:
        df = df[df["commodity"].astype(str).str.strip().str.casefold() == "rice"]
    if args.end_date and "arrival_date" in df.columns:
        dates = pd.to_datetime(df["arrival_date"], dayfirst=True, errors="coerce")
        df = df[dates <= pd.Timestamp(args.end_date)]

    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")

    meta = out.with_suffix(".meta.json")
    meta.write_text(json.dumps({
        "source": "Government of India OGD / AGMARKNET",
        "resource_id": args.resource_id,
        "filters": filters,
        "rows": int(len(df)),
        "raw_columns": list(df.columns),
    }, indent=2), encoding="utf-8")
    print(f"Saved {len(df):,} raw rows to {out}")


if __name__ == "__main__":
    main()
