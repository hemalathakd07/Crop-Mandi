from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from cropmandi.config import ROOT, get_settings

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXCLUDED_FROM_PRICE_LOAD = {
    "chikkamagaluru_merged.csv",
    "madikeri_merged.csv",
    "sirsi_merged.csv",
}


def _col_row(cell_ref: str) -> tuple[int, int]:
    col, row = "", ""
    for ch in cell_ref:
        if ch.isalpha():
            col += ch
        else:
            row += ch
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n - 1, int(row) - 1


def read_xlsx_grid(path: Path) -> list[list[str]]:
    with ZipFile(path) as zf:
        ss: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                texts = [t.text or "" for t in si.findall(".//m:t", NS)]
                ss.append("".join(texts))
        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        rows: dict[int, dict[int, str]] = {}
        for c in sheet.findall(".//m:c", NS):
            ref = c.attrib.get("r")
            if not ref:
                continue
            ci, ri = _col_row(ref)
            t = c.attrib.get("t")
            v = c.find("m:v", NS)
            if v is None or v.text is None:
                val = ""
            elif t == "s":
                val = ss[int(v.text)]
            else:
                val = v.text
            rows.setdefault(ri, {})[ci] = val
        if not rows:
            return []
        maxr = max(rows)
        maxc = max(max(r.keys()) for r in rows.values() if r)
        return [[rows.get(r, {}).get(c, "") for c in range(maxc + 1)] for r in range(maxr + 1)]


def read_xlsx(path: Path) -> list[dict]:
    grid = read_xlsx_grid(path)
    if not grid:
        return []
    headers = [str(h).strip() or f"col_{i}" for i, h in enumerate(grid[0])]
    data = []
    for row in grid[1:]:
        if all(str(x).strip() == "" for x in row):
            continue
        data.append({headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))})
    return data


def parse_date(value) -> date | None:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        serial = float(text)
        if 20000 < serial < 80000:
            return date(1899, 12, 30) + timedelta(days=int(serial))
    except ValueError:
        return None
    return None


def _numbers(values: list[str]) -> list[float]:
    out = []
    for value in values:
        text = str(value).replace(",", "").strip()
        if text in {"", "-", "None"}:
            continue
        if "-" in text and not text.startswith("-"):
            continue
        try:
            out.append(float(text))
        except ValueError:
            continue
    return out


def longest_constant_run(values: list[float]) -> int:
    if not values:
        return 0
    best = run = 1
    for i in range(1, len(values)):
        if values[i] == values[i - 1]:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def audit_rows(name: str, rows: list[dict], *, classification: str) -> dict:
    if not rows:
        return {"file": name, "row_count": 0, "classification": classification}
    cols = list(rows[0].keys())
    missing = {c: sum(1 for r in rows if str(r.get(c, "")).strip() == "") for c in cols}
    date_col = next((c for c in cols if "date" in c.lower()), cols[0])
    dates = [parse_date(r.get(date_col, "")) for r in rows]
    parsed_dates = [d for d in dates if d]
    price_col = next(
        (c for c in cols if any(x in c.lower() for x in ("price", "avg", "rate"))),
        cols[-1],
    )
    prices = _numbers([str(r.get(price_col, "")) for r in rows])
    markets = sorted({str(r.get(c, "")).strip() for r in rows for c in cols if "market" in c.lower() or c.lower() == "region"} - {""})
    types = sorted({str(r.get(c, "")).strip() for r in rows for c in cols if c.lower() in {"type", "grade"} or "type" in c.lower()} - {""})
    commodity_explicit = any("coffee" in c.lower() or "pepper" in c.lower() for c in cols) or any(
        "coffee" in str(v).lower() or "pepper" in str(v).lower()
        for r in rows[:5]
        for v in r.values()
    )
    source_present = any("source" in c.lower() or "url" in c.lower() for c in cols)
    blob = " ".join(cols).lower()
    unit_guess = None
    if "50" in blob and "kg" in blob:
        unit_guess = "possibly Rs/50 kg from a header row"
    report = {
        "file": name,
        "classification": classification,
        "row_count": len(rows),
        "columns": cols,
        "missing_values": missing,
        "date_range": [str(min(parsed_dates)), str(max(parsed_dates))] if parsed_dates else None,
        "unique_dates": len(set(parsed_dates)),
        "duplicate_full_rows": len(rows) - len({tuple(sorted(r.items())) for r in rows}),
        "unique_markets": markets,
        "unique_types": types[:50],
        "unique_prices": len(set(prices)),
        "price_range": [min(prices), max(prices)] if prices else None,
        "units": unit_guess,
        "commodity_explicitly_identified": commodity_explicit,
        "source_provenance_available": source_present,
        "suspicious_constant_price_run": longest_constant_run(prices),
        "suspicious_values": {
            "non_numeric_or_range_prices": len(rows) - len(prices),
            "very_low_prices": sum(1 for p in prices if p < 100),
        },
        "eligible_for_production_price_table": False,
        "notes": [],
    }
    if name in EXCLUDED_FROM_PRICE_LOAD:
        report["notes"].append(
            "EXCLUDED: merged CSV Price column must not be used as coffee or pepper market prices."
        )
        report["commodity_explicitly_identified"] = False
        report["source_provenance_available"] = False
        report["units"] = "not stated"
    if classification == "UNVERIFIED_LOCAL_DATA":
        report["notes"].append(
            "Not Coffee Board or Spices Board data. Provenance not established."
        )
    if prices:
        report["price_mean"] = round(statistics.mean(prices), 2)
    return report


def main() -> None:
    files = [
        (ROOT / "coffee_market_price.xlsx", "UNVERIFIED_LOCAL_DATA"),
        (ROOT / "pepper_market_price.xlsx", "UNVERIFIED_LOCAL_DATA"),
        (ROOT / "chikkamagaluru_merged.csv", "EXCLUDED_MERGED_CSV"),
        (ROOT / "madikeri_merged.csv", "EXCLUDED_MERGED_CSV"),
        (ROOT / "sirsi_merged.csv", "EXCLUDED_MERGED_CSV"),
    ]
    reports = []
    for path, classification in files:
        if not path.exists():
            reports.append({"file": path.name, "error": "missing"})
            continue
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
        else:
            rows = read_xlsx(path)
        reports.append(audit_rows(path.name, rows, classification=classification))
    out = get_settings().data_dir / "audit" / "dataset_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
    print(json.dumps(reports, indent=2, default=str))


if __name__ == "__main__":
    main()
