"""One-command Karnataka Rice extraction + cleaning pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    cmd = [sys.executable, *args]
    print("\n>>> " + " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start-date", help="Optional lower bound YYYY-MM-DD for local cleaning")
    p.add_argument("--max-date", help="Optional upper bound YYYY-MM-DD for local cleaning")
    p.add_argument("--max-rows", type=int)
    args = p.parse_args()

    run("scripts/fetch_rice_karnataka.py", *(sum((["--max-rows", str(args.max_rows)] if args.max_rows else []), [])))
    clean_args = []
    if args.start_date:
        clean_args += ["--min-date", args.start_date]
    if args.max_date:
        clean_args += ["--max-date", args.max_date]
    run("scripts/clean_rice_data.py", *clean_args)
    print("\nDONE: data/clean/karnataka_rice_prices.csv")


if __name__ == "__main__":
    main()
