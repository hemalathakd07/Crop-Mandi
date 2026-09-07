"""Series registry and provenance labels for experimental models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


COFFEE_DATA_STATUS = "UNVERIFIED_HISTORICAL_COFFEE_DATA"
COFFEE_DATA_USAGE = "EXPERIMENTAL_ONLY"

COFFEE_SOURCE_COLUMNS = {
    "arabica_parchment": "Arabica_Parchment_50KG",
    "arabica_cherry": "Arabica_Cherry_50KG",
    "robusta_parchment": "Robusta_Parchment_50KG",
    "robusta_cherry": "Robusta_Cherry_50KG",
}

COFFEE_DISPLAY = {
    "arabica_parchment": "Arabica Parchment",
    "arabica_cherry": "Arabica Cherry",
    "robusta_parchment": "Robusta Parchment",
    "robusta_cherry": "Robusta Cherry",
}

PEPPER_SERIES_IDS = (
    "pepper_cochin_garbled",
    "pepper_cochin_ungarbled",
    "pepper_sirsi",
)

MIN_RAW_OBSERVATIONS = 40
MIN_SUPERVISED_ROWS = 30


@dataclass
class PriceSeries:
    series_id: str
    display_name: str
    commodity: str
    dates: list[date]
    prices: list[float]
    unit: str
    provenance: dict[str, Any] = field(default_factory=dict)
    use_target_session_calendar: bool = False

    def __post_init__(self) -> None:
        if len(self.dates) != len(self.prices):
            raise ValueError("dates and prices length mismatch")


def coffee_provenance(source_file: str, grade_column: str) -> dict[str, Any]:
    return {
        "data_status": COFFEE_DATA_STATUS,
        "data_usage": COFFEE_DATA_USAGE,
        "official_coffee_board": False,
        "official_mandi": False,
        "source_file": source_file,
        "grade_column": grade_column,
        "unit_basis": "Rs/50 kg as named in the source columns; no unit conversion",
        "weekend_policy": "Saturday and Sunday rows removed; no interpolation",
        "target_rule": (
            "Next published session is the next weekday in the filtered series. "
            "This workbook has a price on every calendar weekday, so that is the "
            "next Monday–Friday after the last observed date. Not the next calendar "
            "day when the last session is Friday."
        ),
        "warning": (
            "Unverified historical coffee spreadsheet. Not Coffee Board data, "
            "not official market data, and not official mandi data."
        ),
    }


def pepper_provenance(
    *,
    market_name: str,
    market_kind: str,
    grade_code: str,
    unit: str,
    price_type: str,
    source_code: str,
    source_name: str,
    publisher_source_label: str | None,
) -> dict[str, Any]:
    return {
        "data_status": "SPICES_BOARD_INGESTED",
        "data_usage": "EXPERIMENTAL_ML_ON_VALIDATED_OBSERVATIONS",
        "market_name": market_name,
        "market_kind": market_kind,
        "grade_code": grade_code,
        "unit": unit,
        "price_type": price_type,
        "source_code": source_code,
        "source_name": source_name,
        "publisher_source_label": publisher_source_label,
        "indicative_not_transaction": True,
        "target_rule": (
            "Next published session is the next actual observation date in this "
            "series after the latest known date. Gaps are not filled. The calendar "
            "date of the next session is unknown until it is published."
        ),
        "warning": (
            "Spices Board indicative daily averages are not guaranteed transaction prices. "
            "Cochin and Sirsi are separate markets and must not be combined."
        ),
    }


def rice_provenance(
    *,
    market_name: str,
    market_kind: str,
    grade_code: str,
    unit: str,
    price_type: str,
    source_code: str,
    source_name: str,
    publisher_source_label: str | None,
    variety: str | None = None,
    raw_commodity: str = "Rice",
) -> dict[str, Any]:
    return {
        "data_status": "AGMARKNET_INGESTED",
        "data_usage": "EXPERIMENTAL_ML_ON_VALIDATED_OBSERVATIONS",
        "market_name": market_name,
        "market_kind": market_kind,
        "grade_code": grade_code,
        "variety": variety,
        "raw_commodity": raw_commodity,
        "unit": unit,
        "price_type": price_type,
        "source_code": source_code,
        "source_name": source_name,
        "publisher_source_label": publisher_source_label,
        "source": "AGMARKNET / data.gov.in (Directorate of Marketing and Inspection, Ministry of Agriculture and Farmers Welfare, Government of India)",
        "indicative_not_transaction": True,
        "target_rule": (
            "Next published session is the next actual observation date in this "
            "market-variety series after the latest known date. Gaps are not "
            "filled. The calendar date of the next session is unknown until it "
            "is published."
        ),
        "warning": (
            "AGMARKNET modal prices are indicative daily mandi prices, not "
            "guaranteed transaction prices. Karnataka data only. Rice and Paddy "
            "are distinct AGMARKNET commodities and are never merged."
        ),
    }
