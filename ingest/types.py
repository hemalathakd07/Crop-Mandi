from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class ParsedObservation:
    commodity_code: str
    market_name: str
    market_kind: str
    market_state: str | None
    market_district: str | None
    grade_code: str
    market_date: date
    price: Decimal
    price_min: Decimal | None
    price_max: Decimal | None
    price_avg: Decimal | None
    unit: str
    price_type: str
    source_code: str
    source_url: str | None
    publisher_source_label: str | None
    notes: str | None = None
    variety: str | None = None
    extras: dict = field(default_factory=dict)


@dataclass
class Rejection:
    reason: str
    row: dict


KNOWN_UNITS = {
    "INR_PER_KG",
    "INR_PER_50KG",
    "INR_PER_QUINTAL",
}

V1_COMMODITIES = {"coffee", "pepper", "rice"}

PEPPER_GRADES = {"UNSPECIFIED", "GARBLED", "UNGARBLED", "UNGRADED", "WHITE"}
COFFEE_GRADES = {
    "UNSPECIFIED",
    "ARABICA_PARCHMENT",
    "ARABICA_CHERRY",
    "ROBUSTA_PARCHMENT",
    "ROBUSTA_CHERRY",
}

RICE_GRADES = {
    "UNSPECIFIED",
}
