from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from ingest.types import COFFEE_GRADES, KNOWN_UNITS, PEPPER_GRADES, RICE_GRADES, V1_COMMODITIES, ParsedObservation, Rejection


def _positive(value: Decimal | None) -> bool:
    return value is not None and value > 0


def validate_observation(
    obs: ParsedObservation,
    *,
    today: date | None = None,
) -> list[str]:
    errors: list[str] = []
    today = today or date.today()

    if obs.commodity_code not in V1_COMMODITIES:
        errors.append("unsupported_or_missing_commodity")
    if not obs.market_name or not str(obs.market_name).strip():
        errors.append("missing_market")
    if not obs.grade_code or not str(obs.grade_code).strip():
        errors.append("missing_grade")
    elif obs.commodity_code == "pepper" and obs.grade_code not in PEPPER_GRADES:
        errors.append("unsupported_pepper_grade")
    elif obs.commodity_code == "coffee" and obs.grade_code not in COFFEE_GRADES:
        errors.append("unsupported_coffee_grade")
    # Rice grades come straight from the AGMARKNET government taxonomy
    # (for example FAQ / SUPEFINE / OTHER). It is an open set, so any
    # non-empty grade is accepted and stored as-is; the source defines it.
    if (
        obs.commodity_code == "rice"
        and not obs.variety
        and not str(obs.variety or "").strip()
    ):
        errors.append("missing_variety")
    if obs.market_date is None:
        errors.append("invalid_date")
    elif obs.market_date > today + timedelta(days=1):
        errors.append("future_date")
    elif obs.market_date.year < 1990:
        errors.append("invalid_date")
    if not _positive(obs.price):
        errors.append("invalid_price")
    if obs.price_min is not None and not _positive(obs.price_min):
        errors.append("invalid_price_min")
    if obs.price_max is not None and not _positive(obs.price_max):
        errors.append("invalid_price_max")
    if obs.price_avg is not None and not _positive(obs.price_avg):
        errors.append("invalid_price_avg")
    if (
        obs.price_min is not None
        and obs.price_max is not None
        and obs.price_min > obs.price_max
    ):
        errors.append("min_greater_than_max")
    if obs.price_min is not None and obs.price is not None and obs.price_min > obs.price:
        errors.append("min_greater_than_modal")
    if obs.price is not None and obs.price_max is not None and obs.price > obs.price_max:
        errors.append("modal_greater_than_max")
    if not obs.unit:
        errors.append("missing_unit")
    elif obs.unit not in KNOWN_UNITS:
        errors.append("unknown_unit_not_converted")
    if not obs.price_type:
        errors.append("missing_price_type")
    if not obs.source_code:
        errors.append("missing_source")
    if obs.source_code in {
        "coffee_board_of_india",
        "spices_board_india",
    } and not obs.source_url:
        errors.append("missing_source_url")
    if obs.commodity_code == "pepper" and obs.unit != "INR_PER_KG":
        # Spices Board publishes Rs/Kg. Do not silently convert other units.
        if obs.source_code == "spices_board_india":
            errors.append("unexpected_pepper_unit")
    if obs.commodity_code == "rice" and obs.unit != "INR_PER_QUINTAL":
        # AGMARKNET publishes Rs/Quintal. Do not silently convert other units.
        if obs.source_code == "agmarknet_data_gov_in":
            errors.append("unexpected_rice_unit")
    return errors


def partition_valid(
    observations: list[ParsedObservation],
) -> tuple[list[ParsedObservation], list[Rejection]]:
    valid: list[ParsedObservation] = []
    rejected: list[Rejection] = []
    for obs in observations:
        errors = validate_observation(obs)
        if errors:
            rejected.append(
                Rejection(
                    reason=";".join(errors),
                    row={"market": obs.market_name, "date": str(obs.market_date)},
                )
            )
        else:
            valid.append(obs)
    return valid, rejected
