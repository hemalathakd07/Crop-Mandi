from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ingest.types import ParsedObservation

SOURCE_URL = "https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"
PRICE_TYPE = "modal_daily"
UNIT = "INR_PER_QUINTAL"


def _parse_decimal(value: str | None) -> Decimal | None:
    """Parse a string to Decimal, returning None for invalid values."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "–", "—", "NA", "N/A", "00.00", "0", "0.00", "0.0"}:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if number <= 0:
        return None
    return number


def _parse_date(value: str | None) -> date | None:
    """Parse date string in various formats."""
    if value is None:
        return None
    text = str(value).strip()
    
    # Try common date formats
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d/%b/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_variety(variety: str | None) -> str | None:
    """Normalize variety name to a consistent format, or None when absent.

    The AGMARKNET resource names the commodity 'Rice' and the crop type
    'Paddy' separately. A missing variety cannot form a market-variety series,
    so it is left as None and rejected by validation instead of fabricated.
    """
    if not variety:
        return None
    text = str(variety).strip().upper()
    if not text or text in {"-", "", "NA", "N/A", "NULL", "NIL"}:
        return None
    # Replace spaces/hyphens with underscores for consistency
    return text.replace(" ", "_").replace("-", "_")


def _normalize_grade(grade: str | None) -> str:
    """Normalize grade name to a consistent format."""
    if not grade:
        return "UNSPECIFIED"
    text = str(grade).strip().upper()
    if not text or text in {"-", "", "NA", "N/A", "NULL", "NIL"}:
        return "UNSPECIFIED"
    return text.replace(" ", "_")


def _normalize_market_name(market: str | None) -> str:
    """Normalize market name."""
    if not market:
        return "UNKNOWN"
    text = str(market).strip()
    if not text:
        return "UNKNOWN"
    # Title case for consistency
    return text.title()


def parse_agmarknet_rice_json(
    json_data: str | dict,
    *,
    source_url: str = SOURCE_URL,
) -> list[ParsedObservation]:
    """Parse AGMARKNET Rice JSON data into ParsedObservation objects."""
    if isinstance(json_data, str):
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            return []
    else:
        data = json_data
    
    records = data.get("records", [])
    if not records:
        return []
    
    observations: list[ParsedObservation] = []
    
    for record in records:
        # Extract required fields
        state = record.get("State")
        district = record.get("District")
        market = record.get("Market")
        commodity = record.get("Commodity")
        variety = record.get("Variety")
        grade = record.get("Grade")
        arrival_date = record.get("Arrival_Date")
        min_price = record.get("Min_Price")
        max_price = record.get("Max_Price")
        modal_price = record.get("Modal_Price")
        
        # Defensive Karnataka + Rice-only filter. AGMARKNET publishes Rice and
        # Paddy as separate commodity rows; Paddy is never merged into Rice.
        if not state or str(state).strip().lower() != "karnataka":
            continue
        if not commodity or str(commodity).strip().lower() != "rice":
            continue
        
        # Parse date
        market_date = _parse_date(arrival_date)
        if market_date is None:
            continue
        
        # Parse prices - prefer modal_price, fall back to min/max
        modal = _parse_decimal(modal_price)
        min_p = _parse_decimal(min_price)
        max_p = _parse_decimal(max_price)
        
        # Modal price is required
        if modal is None:
            continue
        
        # Normalize fields
        market_name = _normalize_market_name(market)
        variety_code = _normalize_variety(variety)
        grade_code = _normalize_grade(grade)
        
        # Market kind - assume mandi for AGMARKNET
        market_kind = "mandi"
        
        # Create observation
        observations.append(
            ParsedObservation(
                commodity_code="rice",
                market_name=market_name,
                market_kind=market_kind,
                market_state="Karnataka",
                market_district=str(district).strip() if district else None,
                grade_code=grade_code,
                variety=variety_code,
                market_date=market_date,
                price=modal,
                price_min=min_p,
                price_max=max_p,
                price_avg=modal,  # Use modal as average
                unit=UNIT,
                price_type=PRICE_TYPE,
                source_code="agmarknet_data_gov_in",
                source_url=source_url,
                publisher_source_label="Directorate of Marketing & Inspection (DMI), Ministry of Agriculture and Farmers Welfare",
                notes=(
                    f"Variety: {variety_code or 'UNSPECIFIED'}. Grade: {grade_code}. "
                    "AGMARKNET modal daily price used as primary."
                ),
                extras={
                    "raw_state": state,
                    "raw_district": district,
                    "raw_market": market,
                    "raw_commodity": commodity,
                    "raw_variety": variety,
                    "raw_grade": grade,
                    "arrival_date": arrival_date,
                    "data_source": "AGMARKNET / data.gov.in",
                },
            )
        )
    
    return observations


def parse_agmarknet_rice_file(path: Path, source_url: str = SOURCE_URL) -> list[ParsedObservation]:
    """Parse AGMARKNET Rice JSON file."""
    return parse_agmarknet_rice_json(path.read_text(encoding="utf-8"), source_url=source_url)