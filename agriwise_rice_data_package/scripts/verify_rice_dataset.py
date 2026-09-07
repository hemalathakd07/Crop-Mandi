"""Sanity-check a cleaned Karnataka Rice dataset before ML training."""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="data/clean/karnataka_rice_prices.csv")
    args = p.parse_args()
    path = ROOT / args.input
    df = pd.read_csv(path, low_memory=False)

    required = ["state","district","market","commodity","variety","arrival_date","modal_price"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"FAIL: missing columns: {missing}")

    d = pd.to_datetime(df["arrival_date"], errors="coerce")
    modal = pd.to_numeric(df["modal_price"], errors="coerce")
    print(f"Rows: {len(df):,}")
    print(f"Date range: {d.min().date() if d.notna().any() else 'N/A'} -> {d.max().date() if d.notna().any() else 'N/A'}")
    print(f"Districts: {df['district'].nunique():,}; Markets: {df['market'].nunique():,}; Varieties: {df['variety'].nunique():,}")
    print(f"Missing modal prices: {int(modal.isna().sum()):,}; non-positive modal prices: {int((modal <= 0).sum()):,}")
    print(f"Duplicate market-day-variety rows: {int(df.duplicated(['state','district','market','commodity','variety','arrival_date']).sum()):,}")

    bad_state = ~df["state"].astype(str).str.casefold().eq("karnataka")
    bad_crop = ~df["commodity"].astype(str).str.casefold().eq("rice")
    if bad_state.any() or bad_crop.any():
        raise SystemExit("FAIL: dataset contains records outside Karnataka/Rice")
    if modal.isna().any() or (modal <= 0).any():
        raise SystemExit("FAIL: invalid modal prices remain")
    print("PASS: dataset is ready for the AgriWise training pipeline.")


if __name__ == "__main__":
    main()
