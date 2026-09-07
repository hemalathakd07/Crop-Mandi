"""Merge raw/clean Rice CSV extracts into one deduplicated ML dataset."""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["state", "district", "market", "commodity", "variety", "grade", "arrival_date"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df["arrival_date"] = pd.to_datetime(df["arrival_date"], errors="coerce")
    for c in ["min_price", "max_price", "modal_price"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", action="append", required=True, help="CSV path; repeat for multiple files")
    p.add_argument("--output", default="data/clean/karnataka_rice_prices.csv")
    args = p.parse_args()

    frames = []
    for name in args.input:
        path = ROOT / name
        df = normalize(pd.read_csv(path, low_memory=False))
        needed = [c for c in KEYS if c not in df.columns]
        if needed:
            raise SystemExit(f"{path}: missing key columns {needed}")
        df = df[df["state"].astype(str).str.casefold().eq("karnataka")]
        df = df[df["commodity"].astype(str).str.casefold().eq("rice")]
        frames.append(df)

    if not frames:
        raise SystemExit("No input files supplied")
    df = pd.concat(frames, ignore_index=True, sort=False)
    df = df.dropna(subset=["arrival_date"])
    if "modal_price" in df.columns:
        df = df[df["modal_price"] > 0]

    # Keep the last copy after sorting by source row order.
    df = df.drop_duplicates(subset=KEYS, keep="last")
    df["arrival_date"] = df["arrival_date"].dt.strftime("%Y-%m-%d")
    preferred = KEYS + ["min_price", "max_price", "modal_price"]
    df = df[[c for c in preferred if c in df.columns]].sort_values(
        ["arrival_date", "district", "market", "variety"], kind="stable"
    )

    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Merged {len(df):,} rows -> {out}")


if __name__ == "__main__":
    main()
