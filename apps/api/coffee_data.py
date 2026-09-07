"""Read experimental Coffee weekday sessions. Never writes the original workbook."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import apps.api.runtime as runtime
from apps.api.catalog import SeriesSpec
from ml.datasets import load_coffee_workbook
from ml.registry import COFFEE_DATA_STATUS, COFFEE_DATA_USAGE, coffee_provenance
from ml.sessions import is_weekday


def _csv_path() -> Path:
    return runtime.COFFEE_CSV_PATH


def load_coffee_points() -> dict[str, list[dict]]:
    path = _csv_path()
    if path.is_file():
        by_id: dict[str, list[dict]] = {}
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                sid = row["series_id"]
                d = date.fromisoformat(row["session_date"])
                if not is_weekday(d):
                    continue
                by_id.setdefault(sid, []).append(
                    {
                        "observation_date": d,
                        "price": float(row["price"]),
                        "unit": row["unit"],
                        "display_name": row.get("display_name") or sid,
                    }
                )
        for sid, points in by_id.items():
            points.sort(key=lambda p: p["observation_date"])
        return by_id

    from cropmandi.config import ROOT

    xlsx = ROOT / runtime.COFFEE_XLSX_NAME
    if not xlsx.is_file():
        return {}
    series = load_coffee_workbook(xlsx)
    out: dict[str, list[dict]] = {}
    for sid, s in series.items():
        out[sid] = [
            {
                "observation_date": d,
                "price": p,
                "unit": s.unit,
                "display_name": s.display_name,
            }
            for d, p in zip(s.dates, s.prices)
            if is_weekday(d)
        ]
    return out


def coffee_history(spec: SeriesSpec, start: date | None, end: date | None) -> list[dict]:
    points = load_coffee_points().get(spec.series_id, [])
    rows = []
    for point in points:
        d = point["observation_date"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        rows.append(point)
    return rows


def coffee_latest(spec: SeriesSpec) -> dict | None:
    points = load_coffee_points().get(spec.series_id, [])
    if not points:
        return None
    last = points[-1]
    return last


def coffee_payload_fields(spec: SeriesSpec) -> dict:
    return {
        "commodity": "coffee",
        "series": spec.display_name,
        "series_id": spec.series_id,
        "source": runtime.COFFEE_XLSX_NAME,
        "price_type": "experimental_unverified_historical",
        "indicative": False,
        "experimental": True,
        "official": False,
        "data_status": COFFEE_DATA_STATUS,
        "data_usage": COFFEE_DATA_USAGE,
        "provenance": coffee_provenance(runtime.COFFEE_XLSX_NAME, spec.display_name),
    }
