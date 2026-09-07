"""Load experimental Coffee sheets and validated Pepper DB series. No production inserts."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from cropmandi.config import ROOT, get_settings
from cropmandi.db.models import Commodity, Grade, Market, PriceObservation, Source
from cropmandi.db.session import make_session_factory
from ml.registry import (
    COFFEE_DISPLAY,
    COFFEE_SOURCE_COLUMNS,
    PriceSeries,
    coffee_provenance,
    pepper_provenance,
    rice_provenance,
)
from ml.sessions import filter_weekdays, is_weekday

COFFEE_XLSX_NAME = "karnataka_daily_coffee_prices_7years.xlsx"
EXPERIMENTAL_DIR = ROOT / "data" / "experimental"


def coffee_xlsx_path() -> Path:
    candidate = ROOT / COFFEE_XLSX_NAME
    if not candidate.is_file():
        raise FileNotFoundError(
            f"Experimental coffee workbook not found at {candidate}. "
            "The original file must not be renamed."
        )
    return candidate


def _parse_cell_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise TypeError(f"cannot parse date from {value!r}")


def load_coffee_workbook(path: Path | None = None) -> dict[str, PriceSeries]:
    """Read the original workbook. Never writes back to it."""
    src = path or coffee_xlsx_path()
    wb = load_workbook(src, read_only=True, data_only=True)
    try:
        ws = wb["Daily Spot Prices"]
        rows = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else "" for c in next(rows)]
        expected = [
            "Date",
            "Day",
            "Arabica_Parchment_50KG",
            "Arabica_Cherry_50KG",
            "Robusta_Parchment_50KG",
            "Robusta_Cherry_50KG",
        ]
        if header[:6] != expected:
            raise ValueError(f"unexpected coffee header: {header[:6]}")
        col_dates: list[date] = []
        col_prices: dict[str, list[float | None]] = {
            key: [] for key in COFFEE_SOURCE_COLUMNS
        }
        for row in rows:
            if not row or row[0] is None:
                continue
            d = _parse_cell_date(row[0])
            col_dates.append(d)
            mapping = {
                "arabica_parchment": row[2],
                "arabica_cherry": row[3],
                "robusta_parchment": row[4],
                "robusta_cherry": row[5],
            }
            for key, raw in mapping.items():
                if raw is None or raw == "":
                    col_prices[key].append(None)
                else:
                    col_prices[key].append(float(raw))
    finally:
        wb.close()

    series: dict[str, PriceSeries] = {}
    for key, column in COFFEE_SOURCE_COLUMNS.items():
        pairs_d: list[date] = []
        pairs_p: list[float] = []
        for d, p in zip(col_dates, col_prices[key]):
            if p is None:
                continue
            pairs_d.append(d)
            pairs_p.append(p)
        week_d, week_p = filter_weekdays(pairs_d, pairs_p)
        series_id = f"coffee_{key}"
        series[series_id] = PriceSeries(
            series_id=series_id,
            display_name=COFFEE_DISPLAY[key],
            commodity="coffee",
            dates=week_d,
            prices=week_p,
            unit="INR_PER_50KG",
            provenance=coffee_provenance(src.name, column),
            use_target_session_calendar=True,
        )
    return series


def write_experimental_coffee_frames(
    series: dict[str, PriceSeries],
    dest_dir: Path | None = None,
) -> Path:
    """Derived weekday modelling tables. Does not copy or overwrite the Excel file."""
    dest = dest_dir or EXPERIMENTAL_DIR
    dest.mkdir(parents=True, exist_ok=True)
    csv_path = dest / "coffee_weekday_sessions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["series_id", "display_name", "session_date", "weekday", "price", "unit"],
        )
        writer.writeheader()
        for s in series.values():
            for d, p in zip(s.dates, s.prices):
                writer.writerow(
                    {
                        "series_id": s.series_id,
                        "display_name": s.display_name,
                        "session_date": d.isoformat(),
                        "weekday": d.strftime("%A"),
                        "price": f"{p:.4f}",
                        "unit": s.unit,
                    }
                )
    meta = {
        "representation": "experimental_modelling_only",
        "source_workbook": COFFEE_XLSX_NAME,
        "source_modified": False,
        "inserted_into_production_db": False,
        "weekend_rows_removed": True,
        "interpolated": False,
        "unit_conversion": False,
        "data_status": "UNVERIFIED_HISTORICAL_COFFEE_DATA",
        "data_usage": "EXPERIMENTAL_ONLY",
        "series": {
            sid: {
                "observations": len(s.dates),
                "start": s.dates[0].isoformat() if s.dates else None,
                "end": s.dates[-1].isoformat() if s.dates else None,
                "weekdays_only": all(is_weekday(d) for d in s.dates),
            }
            for sid, s in series.items()
        },
    }
    (dest / "coffee_modelling_metadata.json").write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
    return csv_path


def _pepper_group_key(market: Market, grade: Grade, obs: PriceObservation, source: Source) -> tuple:
    return (
        market.name.strip().lower(),
        grade.code.strip().upper(),
        obs.unit,
        obs.price_type,
        source.code,
    )


def separate_pepper_series(rows: list[tuple]) -> dict[str, list[tuple]]:
    """
    Bucket Pepper observations without combining markets or grades.

    rows: (PriceObservation, Market, Grade, Source)
    """
    buckets: dict[tuple, list[tuple]] = defaultdict(list)
    for obs, market, grade, source in rows:
        buckets[_pepper_group_key(market, grade, obs, source)].append(
            (obs, market, grade, source)
        )
    return {str(k): v for k, v in buckets.items()}


def _pick_pepper_targets(
    grouped: dict[str, list[tuple]],
) -> dict[str, list[tuple]]:
    """Map Cochin Garbled, Cochin Ungarbled, and Sirsi (largest Sirsi grade series)."""
    chosen: dict[str, list[tuple]] = {}
    sirsi_candidates: list[tuple[int, str, list[tuple]]] = []
    for key, items in grouped.items():
        _obs0, market, grade, _src = items[0]
        mname = market.name.strip().lower()
        gcode = grade.code.strip().upper()
        if mname == "cochin" and gcode == "GARBLED":
            chosen["pepper_cochin_garbled"] = items
        elif mname == "cochin" and gcode == "UNGARBLED":
            chosen["pepper_cochin_ungarbled"] = items
        elif mname == "sirsi":
            sirsi_candidates.append((len(items), key, items))
    if sirsi_candidates:
        sirsi_candidates.sort(key=lambda x: x[0], reverse=True)
        chosen["pepper_sirsi"] = sirsi_candidates[0][2]
    return chosen


def pepper_series_from_observation_rows(rows: list[tuple]) -> dict[str, PriceSeries]:
    grouped = separate_pepper_series(rows)
    picked = _pick_pepper_targets(grouped)
    labels = {
        "pepper_cochin_garbled": "Cochin Garbled",
        "pepper_cochin_ungarbled": "Cochin Ungarbled",
        "pepper_sirsi": "Sirsi",
    }
    series: dict[str, PriceSeries] = {}
    for sid, items in picked.items():
        items_sorted = sorted(items, key=lambda r: (r[0].market_date, r[0].id))
        dates: list[date] = []
        prices: list[float] = []
        seen_dates: set[date] = set()
        last_source_url = None
        for obs, _m, _g, _s in items_sorted:
            if obs.market_date in seen_dates:
                continue
            seen_dates.add(obs.market_date)
            dates.append(obs.market_date)
            prices.append(float(obs.price))
            last_source_url = obs.source_url
        obs0, market, grade, source = items_sorted[0]
        series[sid] = PriceSeries(
            series_id=sid,
            display_name=labels[sid],
            commodity="pepper",
            dates=dates,
            prices=prices,
            unit=obs0.unit,
            provenance=pepper_provenance(
                market_name=market.name,
                market_kind=market.kind,
                grade_code=grade.code,
                unit=obs0.unit,
                price_type=obs0.price_type,
                source_code=source.code,
                source_name=source.name,
                publisher_source_label=obs0.publisher_source_label,
            ),
            use_target_session_calendar=False,
        )
        series[sid].provenance["source_url"] = last_source_url
        series[sid].provenance["observations_in_group"] = len(items_sorted)
        series[sid].provenance["unique_session_dates"] = len(dates)
        if sid == "pepper_sirsi":
            series[sid].provenance["sirsi_grade_used"] = grade.code
            series[sid].provenance["sirsi_note"] = (
                "Largest Sirsi grade series only; other Sirsi grades are not merged."
            )
    return series


def _slugify(value: str, max_len: int = 28) -> str:
    """DJB-style slug for stable series ids. Never encodes personal data."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower().strip()).strip("_")
    return slug[:max_len].strip("_") or "unknown"


def _rice_variety_display(code: str) -> str:
    """Readable AGMARKNET variety label (IR_64 -> 'IR 64', PONNI -> 'Ponni')."""
    words = []
    for part in str(code or "GENERAL").split("_"):
        if part and part.isupper() and len(part) <= 4:
            words.append(part)
        else:
            words.append(part.title())
    return " ".join(words)


def _rice_group_key(obs: PriceObservation, market: Market, grade: Grade, source: Source) -> tuple:
    return (
        market.name.strip().lower(),
        grade.code.strip().upper(),
        str(obs.variety or "").strip().upper(),
        obs.unit,
        obs.price_type,
        source.code,
    )


def rice_series_from_observation_rows(rows: list[tuple]) -> dict[str, PriceSeries]:
    """Bucket Rice observations into market + variety series.

    AGMARKNET rice records carry a market and a variety (for example
    'Mangalore' + 'IR-64'). Groups preserve every market-variety-priced grade;
    nothing is pooled across markets or varieties.
    """
    buckets: dict[tuple, list[tuple]] = defaultdict(list)
    for obs, market, grade, source in rows:
        buckets[_rice_group_key(obs, market, grade, source)].append(
            (obs, market, grade, source)
        )

    series: dict[str, PriceSeries] = {}
    for key, items in buckets.items():
        mname, gcode, variety_code, unit, ptype, scode = key
        items_sorted = sorted(items, key=lambda r: (r[0].market_date, r[0].id))

        # Stable series id, e.g. rice_mangalore_ir_64. The grade is appended
        # only when it is a real AGMARKNET grade so distinct grades stay apart.
        sid = f"rice_{_slugify(mname)}_{_slugify(variety_code)}"
        if gcode and gcode != "UNSPECIFIED":
            sid = f"{sid}_{_slugify(gcode)}"

        dates: list[date] = []
        prices: list[float] = []
        seen_dates: set[date] = set()
        last_source_url = None
        for obs, _m, _g, _s in items_sorted:
            if obs.market_date in seen_dates:
                continue
            seen_dates.add(obs.market_date)
            dates.append(obs.market_date)
            prices.append(float(obs.price))
            last_source_url = obs.source_url
        if not dates:
            continue

        obs0, market, grade, source = items_sorted[0]
        variety_display = _rice_variety_display(variety_code) if variety_code else "General"
        display = f"{market.name.title()} {variety_display}"
        series[sid] = PriceSeries(
            series_id=sid,
            display_name=display,
            commodity="rice",
            dates=dates,
            prices=prices,
            unit=obs0.unit,
            provenance=rice_provenance(
                market_name=market.name,
                market_kind=market.kind,
                grade_code=grade.code,
                variety=variety_code or None,
                unit=obs0.unit,
                price_type=obs0.price_type,
                source_code=source.code,
                source_name=source.name,
                publisher_source_label=obs0.publisher_source_label,
            ),
            use_target_session_calendar=False,
        )
        series[sid].provenance["source_url"] = last_source_url
        series[sid].provenance["observations_in_group"] = len(items_sorted)
        series[sid].provenance["unique_session_dates"] = len(dates)
    return series


def load_pepper_from_db(database_url: str | None = None) -> dict[str, PriceSeries]:
    settings = get_settings()
    factory = make_session_factory(database_url or settings.database_url)
    session = factory()
    try:
        commodity = session.query(Commodity).filter_by(code="pepper").one_or_none()
        if commodity is None:
            return {}
        rows = (
            session.query(PriceObservation, Market, Grade, Source)
            .join(Market, PriceObservation.market_id == Market.id)
            .join(Grade, PriceObservation.grade_id == Grade.id)
            .join(Source, PriceObservation.source_id == Source.id)
            .filter(PriceObservation.commodity_id == commodity.id)
            .order_by(PriceObservation.market_date.asc(), PriceObservation.id.asc())
            .all()
        )
    finally:
        session.close()
    return pepper_series_from_observation_rows(rows)


def load_rice_from_db(database_url: str | None = None) -> dict[str, PriceSeries]:
    """Load Rice observations from database following same pattern as Pepper."""
    settings = get_settings()
    factory = make_session_factory(database_url or settings.database_url)
    session = factory()
    try:
        commodity = session.query(Commodity).filter_by(code="rice").one_or_none()
        if commodity is None:
            return {}
        rows = (
            session.query(PriceObservation, Market, Grade, Source)
            .join(Market, PriceObservation.market_id == Market.id)
            .join(Grade, PriceObservation.grade_id == Grade.id)
            .join(Source, PriceObservation.source_id == Source.id)
            .filter(PriceObservation.commodity_id == commodity.id)
            .order_by(PriceObservation.market_date.asc(), PriceObservation.id.asc())
            .all()
        )
    finally:
        session.close()
    return rice_series_from_observation_rows(rows)
