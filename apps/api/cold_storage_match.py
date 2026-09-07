"""Resolve farmer query locations and classify exact vs nearby cold-storage matches."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from cropmandi.config import ROOT

LOCATIONS_PATH = ROOT / "datasets" / "farmer_query_locations.csv"
COORDINATES_PATH = ROOT / "datasets" / "cold_storage_coordinates.csv"

# Query aliases only. Does not change the market-centre dropdown values.
LOCATION_ALIASES: dict[str, str] = {
    "sakleshpur": "Sakleshpur",
    "sakleshpura": "Sakleshpur",
    "ballupete": "Ballupete",
    "ballupet": "Ballupete",
    "gendehalli": "Gendehalli",
    "gudugalale": "Gudugalale",
    "gudugale": "Gudugalale",
    "hanbalu": "Hanbalu",
    "hanbal": "Hanbalu",
    "hassan": "Hassan",
    "kodlipete": "Kodlipete",
    "kumbarahalli": "Kumbarahalli",
    "kumbrahalli": "Kumbarahalli",
    "kuniganahalli": "Kuniganahalli",
    "kuninganahalli": "Kuniganahalli",
    "kushalnagar": "Kushalnagar",
    "kushalnagara": "Kushalnagar",
    "madikeri": "Madikeri",
    "makkandur": "Makkandur",
    "mudigere": "Mudigere",
    "pattadur": "Pattadur",
    "somwarpet": "Somwarpet",
    "somawarpet": "Somwarpet",
    "theni": "Theni",
    "chikkamagaluru": "Chikkamagaluru",
    "chikmagaluru": "Chikkamagaluru",
    "chikmagalur": "Chikkamagaluru",
}

EXCLUDED_NAME_TOKENS = (
    "warehouse",
    "warehousing",
    "godown",
    "spinning mill",
    "kswc",
    "supermarket",
    "curing",
)

COLD_NAME_TOKENS = ("cold storage", "cold-storage", "cold chain", "refrigerat", "temperature controlled")


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def load_query_locations(path: Path | None = None) -> dict[str, dict[str, Any]]:
    file_path = path or LOCATIONS_PATH
    rows: dict[str, dict[str, Any]] = {}
    if not file_path.exists():
        return rows
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            name = (raw.get("canonical_name") or raw.get("name") or "").strip()
            if not name:
                continue
            lat = raw.get("latitude")
            lon = raw.get("longitude")
            rows[name] = {
                "name": name,
                "state": (raw.get("state") or "").strip(),
                "district": (raw.get("district") or "").strip(),
                "taluk": (raw.get("taluk") or "").strip(),
                "latitude": float(lat) if lat not in (None, "") else None,
                "longitude": float(lon) if lon not in (None, "") else None,
                "coordinates_source": (raw.get("coordinates_source") or "").strip(),
                "coordinates_precision": (raw.get("coordinates_precision") or "").strip(),
                "notes": (raw.get("notes") or "").strip(),
            }
    return rows


def load_coordinate_overlay(path: Path | None = None) -> dict[str, dict[str, Any]]:
    file_path = path or COORDINATES_PATH
    overlay: dict[str, dict[str, Any]] = {}
    if not file_path.exists():
        return overlay
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            name = _norm(raw.get("name"))
            if not name:
                continue
            overlay[name] = {
                "latitude": float(raw["latitude"]),
                "longitude": float(raw["longitude"]),
                "coordinates_source": (raw.get("coordinates_source") or "").strip(),
                "notes": (raw.get("notes") or "").strip(),
            }
    return overlay


def resolve_query_location(name: str, catalog: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    catalog = catalog if catalog is not None else load_query_locations()
    key = _norm(name)
    canonical = LOCATION_ALIASES.get(key)
    if canonical and canonical in catalog:
        return catalog[canonical]
    for loc_name, row in catalog.items():
        if _norm(loc_name) == key:
            return row
    return None


def is_cold_storage_facility(record: dict[str, Any]) -> bool:
    name = _norm(record.get("name"))
    if not name:
        return False
    if any(token in name for token in EXCLUDED_NAME_TOKENS):
        return False
    if any(token in name for token in COLD_NAME_TOKENS):
        return True
    return False


def is_exact_facility(record: dict[str, Any], location: dict[str, Any]) -> bool:
    loc_name = _norm(location.get("name"))
    loc_district = _norm(location.get("district"))
    haystack = " ".join(
        _norm(record.get(field))
        for field in ("village", "taluk", "district", "address", "name")
    )
    if loc_name and loc_name in haystack:
        # Theni/Hassan city names should not match a different state's district-only string incorrectly.
        record_state = _norm(record.get("state"))
        loc_state = _norm(location.get("state"))
        if loc_state and record_state and loc_state != record_state:
            return False
        return True
    if loc_district and _norm(record.get("district")) == loc_district:
        record_state = _norm(record.get("state"))
        loc_state = _norm(location.get("state"))
        if loc_state and record_state and loc_state != record_state:
            return False
        # District-equal is exact only when the requested place is the district HQ
        # (same name as the district), e.g. Hassan / Theni / Chikkamagaluru.
        return loc_name == loc_district
    return False


def match_type_for_distance(distance_km: float, exact: bool) -> str:
    if exact:
        return "EXACT"
    if distance_km <= 25:
        return "NEARBY"
    if distance_km <= 50:
        return "NEARBY"
    if distance_km <= 75:
        return "DISTRICT_NEARBY"
    return "NO_DATA"


def overall_match_type(types: list[str]) -> str:
    order = ("EXACT", "NEARBY", "DISTRICT_NEARBY")
    for item in order:
        if item in types:
            return item
    return "NO_DATA"
