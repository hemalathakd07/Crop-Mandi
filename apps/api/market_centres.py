"""Explicit market-centre to canonical-location mapping for local Excel workbooks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import apps.api.runtime as runtime
from apps.api.errors import ApiError
from ingest.audit_datasets import _numbers, parse_date, read_xlsx_grid

INVALID_COFFEE_DATE = date(1970, 1, 1)
DATA_STATUS = "UNVERIFIED_LOCAL_DATA"
DATA_USAGE = "LOCAL_MARKET_CENTRE_DATA"
SOURCE_PROVENANCE = "local/unverified market-centre data"

COFFEE_UNIT = "Rs./50 Kg"


@dataclass(frozen=True)
class MarketCentreMapping:
    commodity: str
    canonical_location: str
    raw_market_centre: str
    source_workbook: str
    reason: str = ""
    ambiguous: bool = False


def normalize_centre(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def normalize_location_key(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").split()).casefold()


# Location-name aliases used for UI display and query matching. Not trader names.
LOCATION_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("coffee", "Sakleshpur"): ("Sakleshpura", "Sakleshpur", "SAKLESHPUR"),
    ("coffee", "Chikkamagaluru"): ("Chikkamagaluru", "Chikmagaluru", "Chikmagalur", "CKMG"),
    ("coffee", "Ballupete"): ("Ballupete", "Ballupet"),
    ("coffee", "Somwarpet"): ("Somwarpete", "Somawarpet", "Somwarpet"),
    ("coffee", "Kushalnagar"): ("Kushalnagara", "Kushalnagar"),
    ("pepper", "Balupet"): ("Balupet",),
    ("pepper", "Chikmagalur"): ("Chikmagalur",),
    ("pepper", "Sakleshpur"): ("Sakleshpur",),
    ("pepper", "Kushalnagar"): ("Kushalnagar", "Kushalnagara"),
    ("pepper", "Somwarpet"): ("Somwarpet",),
    ("pepper", "Kumbarahalli"): ("Kumbarahalli",),
    ("pepper", "Hanbalu"): ("Hanbalu",),
}

UNMAPPED_RAW: dict[str, frozenset[str]] = {
    "coffee": frozenset(
        {
            "GOLDEN COFFEE AGENCIES",
            "WESTERN COFFEE CURERS EXPORTS PVT LIMITED",
            "PAI COMM0DITY",
        }
    ),
    "pepper": frozenset(),
}


def _m(
    commodity: str,
    canonical: str,
    raw: str,
    *,
    reason: str = "",
    ambiguous: bool = False,
) -> MarketCentreMapping:
    workbook = runtime.COFFEE_MARKET_XLSX_NAME if commodity == "coffee" else runtime.PEPPER_MARKET_XLSX_NAME
    return MarketCentreMapping(
        commodity=commodity,
        canonical_location=canonical,
        raw_market_centre=raw,
        source_workbook=workbook,
        reason=reason,
        ambiguous=ambiguous,
    )


# Explicit mappings only. Dual-place strings are listed under every supported token.
MAPPINGS: tuple[MarketCentreMapping, ...] = (
    # Coffee — Sakleshpur
    _m("coffee", "Sakleshpur", "GAIN COFEE SAKLESHPURA", reason="Sakleshpura alias"),
    _m("coffee", "Sakleshpur", "LIKITHA COFFEE SAKLESHPURA", reason="Sakleshpura alias"),
    _m("coffee", "Sakleshpur", "NASIR TRADERS SAKLESHPURA", reason="Sakleshpura alias"),
    _m(
        "coffee",
        "Sakleshpur",
        "MD COFFEE KUMBARAHALLI SAKLESHPUR-8495875252",
        reason="dual-place: Kumbarahalli and Sakleshpur",
        ambiguous=True,
    ),
    # Coffee — Kumbarahalli (kept separate from Sakleshpur)
    _m(
        "coffee",
        "Kumbarahalli",
        "MD COFFEE KUMBARAHALLI SAKLESHPUR-8495875252",
        reason="dual-place: Kumbarahalli and Sakleshpur",
        ambiguous=True,
    ),
    # Coffee — Chikkamagaluru
    _m("coffee", "Chikkamagaluru", "SANGAM CURING CHIKKAMAGALURU"),
    _m("coffee", "Chikkamagaluru", "SARAGOD CURING WORKS CHIKKAMAGALURU"),
    _m("coffee", "Chikkamagaluru", "SARATHY COFFEE CURING WORKS CHIKKAMAGALURU"),
    _m("coffee", "Chikkamagaluru", "PANCHAMEE COFFEE CURERS CHIKKAMAGALURU"),
    _m(
        "coffee",
        "Chikkamagaluru",
        "PANCHAMEE COFFEE CURERS CKMG",
        reason="CKMG alias only because PANCHAMEE COFFEE CURERS shares the Chikkamagaluru name",
    ),
    _m("coffee", "Chikkamagaluru", "MR.Stany Golden Coffee Agencies-Chikmagaluru-08262", reason="Chikmagaluru spelling"),
    _m("coffee", "Chikkamagaluru", "COFFEE AGENCY,M.B.G Curers,Chikmagaluru-9844077150", reason="Chikmagaluru spelling"),
    # Coffee — Ballupete
    _m("coffee", "Ballupete", "COFFEE AGENCY BALLUPETE"),
    _m("coffee", "Ballupete", "Geetha Trading Company-Ballupet", reason="Ballupet spelling"),
    # Coffee — others
    _m("coffee", "Mudigere", "HADHI COFEE LINKS MUDIGERE"),
    _m("coffee", "Mudigere", "Best Coffee N Spices Mudigere 9901525254"),
    _m("coffee", "Mudigere", "Mudremane Coffee-Mudigere-9448157051,7353738798"),
    _m(
        "coffee",
        "Mudigere",
        "Pattadur Coffee And Spices-Mudigere-9483129339",
        reason="dual-place: Pattadur and Mudigere",
        ambiguous=True,
    ),
    _m(
        "coffee",
        "Pattadur",
        "Pattadur Coffee And Spices-Mudigere-9483129339",
        reason="dual-place: Pattadur and Mudigere",
        ambiguous=True,
    ),
    _m("coffee", "Somwarpet", "Black Spices-Somwarpete-8453881821", reason="Somwarpete spelling"),
    _m("coffee", "Somwarpet", "MOUNTAIN BLUE SOMAWARPET", reason="Somawarpet spelling"),
    _m("coffee", "Kushalnagar", "JEELANI COFFEE LINKS KUSHALNAGARA", reason="Kushalnagara spelling"),
    _m(
        "coffee",
        "Kushalnagar",
        "SUVARNA COFFEE KUSHALNAGAR MAKKANDUR",
        reason="dual-place: Kushalnagar and Makkandur",
        ambiguous=True,
    ),
    _m(
        "coffee",
        "Makkandur",
        "SUVARNA COFFEE KUSHALNAGAR MAKKANDUR",
        reason="dual-place: Kushalnagar and Makkandur",
        ambiguous=True,
    ),
    _m("coffee", "Madikeri", "SPICE N SPICE MADIKERI"),
    _m("coffee", "Madikeri", "SPICE N SPICE MADIKERI 9448121045"),
    _m("coffee", "Kuniganahalli", "Likitha Coffee Trade Company-Kuniganahalli-9845616"),
    _m(
        "coffee",
        "Gudugalale",
        "Mathirappilly Coffee Links Gudugalale Shanivarasan",
        reason="also contains truncated Shanivarasan; not mapped as a second coffee location",
        ambiguous=True,
    ),
    _m("coffee", "Siddapur", "Coorg Trust Spices-Siddapur"),
    _m("coffee", "Gendehalli", "SRI CHAMUNDESHWARI TRADERS AND CURERS GENDEHALLI:"),
    _m("coffee", "Hanbalu", "SUGANDHA COFFEE & SPICES - HANBALU - 8867294527"),
    _m("coffee", "Suntikoppa", "TERRA COFFEE-SUNTIKOPPA-9620028551"),
    _m("coffee", "Kodlipete", "Sri Guru Raghavendra Coffee Traders Kodlipete 9008"),
    _m("coffee", "Theni", "Arrow Spices-Theni"),
    _m("coffee", "Hassan", "Lakshmi Coffee Curing Works-Hassan-9901124342"),
    _m("coffee", "Hassan", "NKG-Hassan-8884418803"),
    # Pepper — prefix/place tokens from the workbook
    _m("pepper", "Kadaba", "AK Pepper Trading Kadaba"),
    _m("pepper", "Balupet", "Balupet-Coffee Agencies"),
    _m("pepper", "Balupet", "Balupet-Geetha Coffee Trading"),
    _m("pepper", "Balupet", "Balupet-Nanjundeshwara Coffee Agency"),
    _m(
        "pepper",
        "Hosathota",
        "BlackSpices Hosathota Somwarpet-8453881821",
        reason="dual-place: Hosathota and Somwarpet",
        ambiguous=True,
    ),
    _m(
        "pepper",
        "Somwarpet",
        "BlackSpices Hosathota Somwarpet-8453881821",
        reason="dual-place: Hosathota and Somwarpet",
        ambiguous=True,
    ),
    _m("pepper", "Chikmagalur", "Chikmagalur-Arihant Coffee & Spices"),
    _m("pepper", "Chikmagalur", "Chikmagalur-Kiran Commodity"),
    _m("pepper", "Chikmagalur", "Chikmagalur-M.R Stany DSilva-Golden Coffee Agencies"),
    _m("pepper", "Chikmagalur", "Chikmagalur-Nirmal Commodities"),
    _m("pepper", "Chikmagalur", "Chikmagalur-Shantilal-9741230309"),
    _m("pepper", "Gonikoppa", "Gonikoppa-Maruthi Traders Sri Matha Traders"),
    _m("pepper", "Idukki", "Idukki-The Campco Ltd"),
    _m("pepper", "Kushalnagar", "Jeelani Coffee Kushalnagara - 9141825035", reason="explicit Kushalnagara→Kushalnagar alias"),
    _m("pepper", "Kalasa", "Kalasa - CAMPCO LTD"),
    _m("pepper", "Kalasa", "Kalasa - PIB Traders"),
    _m("pepper", "Karkala", "Karkala-Kamadhenu Traders"),
    _m("pepper", "Kuniganahalli", "Kuniganahalli-Likitha Coffee Trading"),
    _m(
        "pepper",
        "Kumbarahalli",
        "MD COFFEE KUMBARAHALLI SAKLESHPUR-8495875252",
        reason="dual-place: Kumbarahalli and Sakleshpur",
        ambiguous=True,
    ),
    _m(
        "pepper",
        "Sakleshpur",
        "MD COFFEE KUMBARAHALLI SAKLESHPUR-8495875252",
        reason="dual-place: Kumbarahalli and Sakleshpur",
        ambiguous=True,
    ),
    _m("pepper", "Madikeri", "Madikeri-Kiran Commodities"),
    _m("pepper", "Madikeri", "Madikeri-Spice N Spice-9448121045"),
    _m("pepper", "Mangalore", "Mangalore - CAMPCO LTD"),
    _m("pepper", "Mangalore", "Mangalore-PB Abdul-7204032229"),
    _m(
        "pepper",
        "Gudugalale",
        "Mathirappilly Coffee Links - Gudugalale Shanivarasanthe",
        reason="dual-place: Gudugalale and Shanivarasanthe",
        ambiguous=True,
    ),
    _m(
        "pepper",
        "Shanivarasanthe",
        "Mathirappilly Coffee Links - Gudugalale Shanivarasanthe",
        reason="dual-place: Gudugalale and Shanivarasanthe",
        ambiguous=True,
    ),
    _m("pepper", "Mudigere", "Mudigere-A.M Traders-9880649375"),
    _m("pepper", "Mudigere", "Mudigere-A1 Traders"),
    _m("pepper", "Mudigere", "Mudigere-Best Coffee N Spices- 9901525254"),
    _m("pepper", "Mudigere", "Mudigere-Bhavarlal Jain"),
    _m("pepper", "Mudigere", "Mudigere-Hadhi Coffee Links"),
    _m("pepper", "Mudigere", "Mudigere-Harshika Traders-9448328846"),
    _m("pepper", "Mudigere", "Mudigere-Malnad"),
    _m("pepper", "Pattadur", "Pattadur Coffee House-9483129339"),
    _m("pepper", "Puttur", "Puttur - CAMPCO LTD"),
    _m("pepper", "Puttur", "Puttur-G.Devanna Kini"),
    _m(
        "pepper",
        "Hanbalu",
        "SUGANDHA COFFEE & SPICES - Hanbalu Sakleshpur - 8867294527",
        reason="dual-place: Hanbalu and Sakleshpur",
        ambiguous=True,
    ),
    _m(
        "pepper",
        "Sakleshpur",
        "SUGANDHA COFFEE & SPICES - Hanbalu Sakleshpur - 8867294527",
        reason="dual-place: Hanbalu and Sakleshpur",
        ambiguous=True,
    ),
    _m("pepper", "Sakleshpur", "Sakleshpur-Gain Coffee Traders"),
    _m("pepper", "Sakleshpur", "Sakleshpur-H.K.G & Bros-9844043907"),
    _m("pepper", "Sakleshpur", "Sakleshpur-Nasir Traders"),
    _m("pepper", "Sakleshpur", "Sakleshpur-Premraj and Sons"),
    _m("pepper", "Sakleshpur", "Sakleshpur-Royal Traders"),
    _m("pepper", "Sakleshpur", "Sakleshpur-S.K Traders"),
    _m("pepper", "Sakleshpur", "Sakleshpur-Sainath Cardamom and Tulsi Spices"),
    _m("pepper", "Sakleshpur", "Sakleshpur-The Cardamom Marketing Company"),
    _m("pepper", "Siddapur", "Siddapur-Trust Spices 9449292511"),
    _m("pepper", "Siddapur", "Super Coffee and Spices Siddapur-9895879123"),
    _m("pepper", "Sirsi", "Sirsi-Kadamba Marketing"),
    _m("pepper", "Kodlipete", "Sri Guru Raghavendra Coffee Traders Kodlipete - 90081 99824"),
    _m("pepper", "Suntikoppa", "Suntikoppa-Terra Coffee"),
    _m("pepper", "Goa", "Goa-Bagayatdar SKVSM"),
)


def _workbook_path(commodity: str) -> Path:
    if commodity == "coffee":
        return runtime.COFFEE_MARKET_XLSX_PATH
    return runtime.PEPPER_MARKET_XLSX_PATH


def _workbook_name(commodity: str) -> str:
    if commodity == "coffee":
        return runtime.COFFEE_MARKET_XLSX_NAME
    return runtime.PEPPER_MARKET_XLSX_NAME


def mappings_for(commodity: str) -> tuple[MarketCentreMapping, ...]:
    return tuple(m for m in MAPPINGS if m.commodity == commodity)


def _rice_markets() -> list[str]:
    """Distinct Karnataka mandi markets with Rice observations in the DB."""
    from cropmandi.config import get_settings
    from cropmandi.db.models import Commodity, Market, PriceObservation
    from cropmandi.db.session import create_all, make_session_factory

    create_all()
    session = make_session_factory(get_settings().database_url)()
    try:
        commodity = session.query(Commodity).filter_by(code="rice").one_or_none()
        if commodity is None:
            return []
        names = (
            session.query(Market.name)
            .join(PriceObservation, PriceObservation.market_id == Market.id)
            .filter(PriceObservation.commodity_id == commodity.id)
            .distinct()
            .order_by(Market.name.asc())
            .all()
        )
        return [row[0] for row in names]
    finally:
        session.close()


def _canonical_names(commodity: str) -> list[str]:
    names = sorted({m.canonical_location for m in mappings_for(commodity)})
    return names


def location_aliases(commodity: str, canonical: str) -> tuple[str, ...]:
    return LOCATION_ALIASES.get((commodity, canonical), (canonical,))


def resolve_location(commodity: str, location: str | None) -> str:
    if not location or not location.strip():
        raise ApiError(
            400,
            "missing_location_parameter",
            "query parameter 'location' is required",
            {"commodity": commodity},
        )
    wanted = normalize_location_key(location)
    if commodity == "rice":
        markets = _rice_markets()
        for name in markets:
            if normalize_location_key(name) == wanted:
                return name
        raise ApiError(
            404,
            "unknown_location",
            f"location '{location}' is not mapped for {commodity}",
            {"commodity": commodity, "supported_locations": markets},
        )
    for canonical in _canonical_names(commodity):
        aliases = location_aliases(commodity, canonical)
        keys = {normalize_location_key(canonical), *(normalize_location_key(a) for a in aliases)}
        if wanted in keys:
            return canonical
    raise ApiError(
        404,
        "unknown_location",
        f"location '{location}' is not mapped for {commodity}",
        {
            "commodity": commodity,
            "supported_locations": _canonical_names(commodity),
        },
    )


def _mapping_index(commodity: str) -> dict[str, list[MarketCentreMapping]]:
    by_raw: dict[str, list[MarketCentreMapping]] = defaultdict(list)
    for mapping in mappings_for(commodity):
        by_raw[normalize_centre(mapping.raw_market_centre)].append(mapping)
    return by_raw


def parse_numeric_price(value) -> float | None:
    """Return a single numeric price, or None for blanks, text, ranges, and OT/EP composites."""
    parsed = _numbers([str(value)])
    if len(parsed) != 1:
        return None
    return parsed[0]


def load_workbook_observations(commodity: str) -> list[dict]:
    path = _workbook_path(commodity)
    if not path.is_file():
        raise ApiError(
            404,
            "market_workbook_missing",
            f"market-centre workbook not found: {path.name}",
            {"commodity": commodity, "file": path.name},
        )
    grid = read_xlsx_grid(path)
    rows: list[dict] = []
    start = 0
    if commodity == "coffee":
        start = 1
    for row in grid[start:]:
        if not row or all(str(x).strip() == "" for x in row):
            continue
        raw_centre = str(row[1] if len(row) > 1 else "").strip()
        if not raw_centre:
            continue
        type_name = str(row[2] if len(row) > 2 else "").strip()
        parsed = parse_date(row[0] if row else "")
        if parsed == INVALID_COFFEE_DATE:
            parsed = None
            invalid_date = True
        else:
            invalid_date = parsed is None and str(row[0] if row else "").strip() != ""
        rows.append(
            {
                "raw_market_centre": raw_centre,
                "type": type_name,
                "observation_date": parsed,
                "price": parse_numeric_price(row[3] if len(row) > 3 else ""),
                "invalid_date": parsed is None,
                "excluded_invalid_date": invalid_date or parsed is None,
            }
        )
    return rows


def locations_payload(commodity: str) -> dict:
    if commodity == "rice":
        markets = _rice_markets()
        return {
            "commodity": commodity,
            "source_workbook": None,
            "data_status": "AGMARKNET_INGESTED",
            "data_usage": "EXPERIMENTAL_ML_ON_VALIDATED_OBSERVATIONS",
            "provenance": "AGMARKNET / data.gov.in",
            "locations": [{"name": name, "raw_variants": [name]} for name in markets],
            "unmapped_raw_centres": [],
        }
    workbook_raw = {normalize_centre(r["raw_market_centre"]) for r in load_workbook_observations(commodity)}
    locations = []
    for name in _canonical_names(commodity):
        locations.append(
            {
                "name": name,
                "raw_variants": list(location_aliases(commodity, name)),
            }
        )
    unmapped = []
    for raw in sorted(UNMAPPED_RAW.get(commodity, ())):
        if normalize_centre(raw) in workbook_raw:
            unmapped.append(raw)
    return {
        "commodity": commodity,
        "source_workbook": _workbook_name(commodity),
        "data_status": DATA_STATUS,
        "data_usage": DATA_USAGE,
        "provenance": SOURCE_PROVENANCE,
        "locations": locations,
        "unmapped_raw_centres": unmapped,
    }


def centres_payload(commodity: str, location: str | None) -> dict:
    canonical = resolve_location(commodity, location)
    observations = load_workbook_observations(commodity)
    by_norm = _mapping_index(commodity)
    seen: dict[str, MarketCentreMapping] = {}
    for obs in observations:
        for mapping in by_norm.get(normalize_centre(obs["raw_market_centre"]), []):
            if mapping.canonical_location == canonical:
                seen[obs["raw_market_centre"]] = mapping
    centres = []
    for raw, mapping in sorted(seen.items(), key=lambda item: item[0].casefold()):
        also = sorted(
            {
                m.canonical_location
                for m in by_norm.get(normalize_centre(raw), [])
                if m.canonical_location != canonical
            }
        )
        centres.append(
            {
                "raw_market_centre": raw,
                "canonical_location": canonical,
                "ambiguous": mapping.ambiguous,
                "reason": mapping.reason or None,
                "also_mapped_to": also,
            }
        )
    return {
        "commodity": commodity,
        "location": canonical,
        "source_workbook": _workbook_name(commodity),
        "data_status": DATA_STATUS,
        "provenance": SOURCE_PROVENANCE,
        "centres": centres,
        "count": len(centres),
    }


def available_payload(commodity: str, location: str | None) -> dict:
    canonical = resolve_location(commodity, location)
    observations = load_workbook_observations(commodity)
    by_norm = _mapping_index(commodity)
    grouped: dict[str, list[dict]] = defaultdict(list)
    mapping_for_raw: dict[str, MarketCentreMapping] = {}
    for obs in observations:
        for mapping in by_norm.get(normalize_centre(obs["raw_market_centre"]), []):
            if mapping.canonical_location == canonical:
                grouped[obs["raw_market_centre"]].append(obs)
                mapping_for_raw[obs["raw_market_centre"]] = mapping
    centres = []
    for raw, rows in sorted(grouped.items(), key=lambda item: item[0].casefold()):
        valid_rows = [r for r in rows if r["observation_date"] is not None]
        valid_dates = [r["observation_date"] for r in valid_rows]
        types = sorted({r["type"] for r in valid_rows if r["type"]})
        mapping = mapping_for_raw[raw]
        also = sorted(
            {
                m.canonical_location
                for m in by_norm.get(normalize_centre(raw), [])
                if m.canonical_location != canonical
            }
        )
        centres.append(
            {
                "raw_market_centre": raw,
                "types": types,
                "date_from": min(valid_dates).isoformat() if valid_dates else None,
                "date_to": max(valid_dates).isoformat() if valid_dates else None,
                "observation_count": len(valid_dates),
                "excluded_invalid_dates": sum(1 for r in rows if r["observation_date"] is None),
                "ambiguous": mapping.ambiguous,
                "reason": mapping.reason or None,
                "also_mapped_to": also,
            }
        )
    return {
        "commodity": commodity,
        "location": canonical,
        "source_workbook": _workbook_name(commodity),
        "data_status": DATA_STATUS,
        "data_usage": DATA_USAGE,
        "provenance": SOURCE_PROVENANCE,
        "unit": COFFEE_UNIT if commodity == "coffee" else None,
        "centres": centres,
        "count": len(centres),
    }


def _rice_prices_payload(location: str | None) -> dict:
    """AGMARKNET Rice observations for one market location from the DB."""
    from cropmandi.config import get_settings
    from cropmandi.db.models import Commodity, Grade, Market, PriceObservation, Source
    from cropmandi.db.session import create_all, make_session_factory

    create_all()
    session = make_session_factory(get_settings().database_url)()
    try:
        commodity = session.query(Commodity).filter_by(code="rice").one_or_none()
        items: list[dict] = []
        if commodity is not None:
            rows = (
                session.query(PriceObservation, Market, Grade, Source)
                .join(Market, PriceObservation.market_id == Market.id)
                .join(Grade, PriceObservation.grade_id == Grade.id)
                .join(Source, PriceObservation.source_id == Source.id)
                .filter(PriceObservation.commodity_id == commodity.id)
                .all()
            )
            for obs, market, grade, source in rows:
                if location and normalize_location_key(market.name) != normalize_location_key(location):
                    continue
                items.append(
                    {
                        "commodity": "rice",
                        "location": market.name,
                        "district": market.district or None,
                        "variety": obs.variety,
                        "grade": grade.code,
                        "price": float(obs.price),
                        "unit": obs.unit,
                        "date": obs.market_date.isoformat(),
                        "source": source.name,
                        "source_code": source.code,
                        "official": True,
                        "data_status": "AGMARKNET_INGESTED",
                    }
                )
        items.sort(key=lambda row: (row["variety"] or "", row["date"]), reverse=True)
        return {
            "commodity": "rice",
            "location": location,
            "source_workbook": None,
            "data_status": "AGMARKNET_INGESTED",
            "data_usage": "EXPERIMENTAL_ML_ON_VALIDATED_OBSERVATIONS",
            "provenance": "AGMARKNET / data.gov.in",
            "unit": "INR_PER_QUINTAL",
            "official": True,
            "observations": items,
            "count": len(items),
        }
    finally:
        session.close()


def prices_payload(commodity: str, location: str | None) -> dict:
    if commodity == "rice":
        canonical = resolve_location(commodity, location)
        return _rice_prices_payload(canonical)
    canonical = resolve_location(commodity, location)
    observations = load_workbook_observations(commodity)
    by_norm = _mapping_index(commodity)
    unit = COFFEE_UNIT if commodity == "coffee" else None
    source = _workbook_name(commodity)
    items: list[dict] = []
    for obs in observations:
        if obs["observation_date"] is None or obs["price"] is None:
            continue
        mappings = by_norm.get(normalize_centre(obs["raw_market_centre"]), [])
        if not any(mapping.canonical_location == canonical for mapping in mappings):
            continue
        items.append(
            {
                "commodity": commodity,
                "location": canonical,
                "market_centre": obs["raw_market_centre"],
                "type": obs["type"],
                "price": obs["price"],
                "unit": unit,
                "date": obs["observation_date"].isoformat(),
                "source": source,
                "official": False,
                "data_status": DATA_STATUS,
            }
        )
    items.sort(key=lambda row: (row["market_centre"].casefold(), row["type"].casefold()))
    items.sort(key=lambda row: row["date"], reverse=True)
    return {
        "commodity": commodity,
        "location": canonical,
        "source_workbook": source,
        "data_status": DATA_STATUS,
        "data_usage": DATA_USAGE,
        "provenance": SOURCE_PROVENANCE,
        "unit": unit,
        "official": False,
        "observations": items,
        "count": len(items),
    }


def is_unmapped(commodity: str, raw_market_centre: str) -> bool:
    return normalize_centre(raw_market_centre) in {
        normalize_centre(r) for r in UNMAPPED_RAW.get(commodity, ())
    }
