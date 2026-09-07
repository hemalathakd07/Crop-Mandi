"""Clean raw Karnataka Rice AGMARKNET data for ML training."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COLUMN_MAP = {
    "state": "state", "district": "district", "market": "market",
    "commodity": "commodity", "variety": "variety", "grade": "grade",
    "arrival_date": "arrival_date", "min_price": "min_price",
    "max_price": "max_price", "modal_price": "modal_price",
    "min_price_rs_quintal": "min_price", "max_price_rs_quintal": "max_price",
    "modal_price_rs_quintal": "modal_price",
}


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    renamed = {c: COLUMN_MAP[c] for c in df.columns if c in COLUMN_MAP}
    df = df.rename(columns=renamed)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/karnataka_rice_agmarknet_raw.csv")
    parser.add_argument("--output", default="data/clean/karnataka_rice_prices.csv")
    parser.add_argument("--min-date")
    parser.add_argument("--max-date")
    args = parser.parse_args()

    inp = ROOT / args.input
    out = ROOT / args.output
    df = standardize(pd.read_csv(inp, low_memory=False))

    required = ["state", "district", "market", "commodity", "variety", "arrival_date", "modal_price"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}. Columns found: {list(df.columns)}")

    for c in ["state", "district", "market", "commodity", "variety", "grade"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

    # Ensure this file is only Karnataka Rice.
    df = df[df["state"].str.casefold().eq("karnataka")]
    df = df[df["commodity"].str.casefold().eq("rice")]

    df["arrival_date"] = pd.to_datetime(df["arrival_date"], dayfirst=True, errors="coerce")
    for c in ["min_price", "max_price", "modal_price"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if args.min_date:
        df = df[df["arrival_date"] >= pd.Timestamp(args.min_date)]
    if args.max_date:
        df = df[df["arrival_date"] <= pd.Timestamp(args.max_date)]

    # Basic quality rules. No imputation.
    df = df.dropna(subset=["arrival_date", "modal_price"])
    df = df[df["modal_price"] > 0]
    if "min_price" in df.columns:
        df.loc[df["min_price"] <= 0, "min_price"] = pd.NA
    if "max_price" in df.columns:
        df.loc[df["max_price"] <= 0, "max_price"] = pd.NA

    if "min_price" in df.columns and "max_price" in df.columns:
        valid_bounds = (
            df["min_price"].isna() | (df["min_price"] <= df["modal_price"]) 
        ) & (
            df["max_price"].isna() | (df["modal_price"] <= df["max_price"])
        )
        df = df[valid_bounds]

    # Exact duplicate market-day-variety records are redundant.
    key = [c for c in ["state", "district", "market", "commodity", "variety", "grade", "arrival_date"] if c in df.columns]
    df = df.drop_duplicates(subset=key, keep="last")

    # Keep a deterministic schema compatible with the current AgriWise model.
    preferred = [
        "state", "district", "market", "commodity", "variety", "grade",
        "arrival_date", "min_price", "max_price", "modal_price"
    ]
    df = df[[c for c in preferred if c in df.columns]]
    df["arrival_date"] = df["arrival_date"].dt.strftime("%Y-%m-%d")
    df = df.sort_values(["arrival_date", "district", "market", "variety"], kind="stable")

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8")

    print(f"Saved {len(df):,} cleaned rows to {out}")
    print(f"Date range: {df['arrival_date'].min()} -> {df['arrival_date'].max()}")
    print(f"Markets: {df['market'].nunique():,}; districts: {df['district'].nunique():,}; varieties: {df['variety'].nunique():,}")


if __name__ == "__main__":
    main()
