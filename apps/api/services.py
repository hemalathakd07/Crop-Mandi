"""Latest, history, and naive next-session estimate helpers."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from apps.api.catalog import (
    SUPPORTED_COMMODITIES,
    SeriesSpec,
    resolve_series,
    series_for,
)
from apps.api.coffee_data import coffee_history, coffee_latest, coffee_payload_fields
from apps.api.errors import ApiError
from apps.api.experiment_metrics import metrics_for
from apps.api.pepper_data import pepper_history, pepper_latest, pepper_payload_fields
from apps.api.rice_data import rice_history, rice_latest, rice_payload_fields
from ml.sessions import next_weekday_session


def parse_commodity(commodity: str | None) -> str:
    if not commodity:
        raise ApiError(400, "unsupported_commodity", "commodity is required")
    code = commodity.strip().lower()
    if code not in SUPPORTED_COMMODITIES:
        raise ApiError(
            400,
            "unsupported_commodity",
            f"commodity '{commodity}' is not supported",
            {"supported": sorted(SUPPORTED_COMMODITIES)},
        )
    return code


def require_series(commodity: str, series: str | None, session=None) -> SeriesSpec:
    if not series or not series.strip():
        raise ApiError(
            400,
            "missing_series_parameter",
            "query parameter 'series' is required",
            {"commodity": commodity},
        )
    spec = resolve_series(commodity, series, session=session)
    if spec is None:
        raise ApiError(
            400,
            "unsupported_series",
            f"series '{series}' is not supported for {commodity}",
            {
                "commodity": commodity,
                "supported_series": [s.display_name for s in series_for(commodity, session=session)],
            },
        )
    return spec


def parse_date_param(value: str | None, field: str) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(
            400,
            "invalid_date_filter",
            f"{field} must be an ISO date YYYY-MM-DD",
        ) from exc


def latest_response(session: Session, commodity: str) -> dict:
    observations = []
    for spec in series_for(commodity, session=session):
        if commodity == "coffee":
            point = coffee_latest(spec)
            if point is None:
                continue
            item = coffee_payload_fields(spec)
            item.update(
                {
                    "price": point["price"],
                    "unit": point["unit"],
                    "observation_date": point["observation_date"].isoformat(),
                }
            )
            observations.append(item)
        elif commodity == "pepper":
            point = pepper_latest(session, spec)
            if point is None:
                continue
            item = pepper_payload_fields(spec, point)
            item.update(
                {
                    "price": point["price"],
                    "unit": point["unit"],
                    "observation_date": point["observation_date"].isoformat(),
                }
            )
            observations.append(item)
        elif commodity == "rice":
            point = rice_latest(session, spec)
            if point is None:
                continue
            item = rice_payload_fields(spec, point)
            item.update(
                {
                    "price": point["price"],
                    "unit": point["unit"],
                    "observation_date": point["observation_date"].isoformat(),
                }
            )
            observations.append(item)
    if not observations:
        raise ApiError(
            404,
            "no_available_observations",
            f"no observations available for {commodity}",
            {"available": False, "commodity": commodity, "observations": [], "reason": "no_verified_observation"},
        )
    return {"available": True, "commodity": commodity, "observations": observations}


def history_response(
    session: Session,
    commodity: str,
    series: str | None,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    spec = require_series(commodity, series, session=session)
    start = parse_date_param(date_from, "from")
    end = parse_date_param(date_to, "to")
    if start and end and start > end:
        raise ApiError(400, "invalid_date_filter", "'from' must be on or before 'to'")

    if commodity == "coffee":
        points = coffee_history(spec, start, end)
        meta = coffee_payload_fields(spec)
    elif commodity == "pepper":
        points = pepper_history(session, spec, start, end)
        meta = pepper_payload_fields(spec, points[-1] if points else None)
    elif commodity == "rice":
        points = rice_history(session, spec, start, end)
        meta = rice_payload_fields(spec, points[-1] if points else None)

    if not points:
        raise ApiError(
            404,
            "no_available_observations",
            "no observations for this series and date filter",
            {"available": False, "commodity": commodity, "series": spec.display_name},
        )

    return {
        "available": True,
        "commodity": commodity,
        "series": spec.display_name,
        "series_id": spec.series_id,
        "unit": points[0]["unit"],
        "interpolated": False,
        "mixed_series": False,
        "count": len(points),
        "data_status": meta["data_status"],
        "data_usage": meta.get("data_usage"),
        "official": False,
        "price_type": meta.get("price_type"),
        "indicative": meta.get("indicative"),
        "experimental": meta.get("experimental"),
        "observations": [
            {
                "observation_date": p["observation_date"].isoformat(),
                "price": p["price"],
                "unit": p["unit"],
            }
            for p in points
        ],
        "provenance": meta.get("provenance"),
    }


def estimate_response(session: Session, commodity: str, series: str | None) -> dict:
    spec = require_series(commodity, series, session=session)
    if commodity == "coffee":
        point = coffee_latest(spec)
        meta = coffee_payload_fields(spec)
        if point is None:
            raise ApiError(
                404,
                "no_available_observations",
                "no coffee observations for this series",
                {"commodity": commodity, "series": spec.display_name},
            )
        latest_price = point["price"]
        latest_date = point["observation_date"]
        target = next_weekday_session(latest_date)
        target_session = target.isoformat()
        next_session_status = "next_weekday_session"
        next_session_known = True
    elif commodity == "pepper":
        point = pepper_latest(session, spec)
        meta = pepper_payload_fields(spec, point)
        if point is None:
            raise ApiError(
                404,
                "no_available_observations",
                "no pepper observations for this series",
                {"commodity": commodity, "series": spec.display_name},
            )
        latest_price = point["price"]
        latest_date = point["observation_date"]
        target_session = None
        next_session_status = "next_published_session_unknown"
        next_session_known = False
    elif commodity == "rice":
        point = rice_latest(session, spec)
        meta = rice_payload_fields(spec, point)
        if point is None:
            raise ApiError(
                404,
                "no_available_observations",
                "no rice observations for this series",
                {"commodity": commodity, "series": spec.display_name},
            )
        latest_price = point["price"]
        latest_date = point["observation_date"]
        target_session = None
        next_session_status = "next_published_session_unknown"
        next_session_known = False

    metrics = metrics_for(spec.series_id)
    estimate = latest_price  # naive last-value; not an ML forecast
    return {
        "commodity": commodity,
        "series": spec.display_name,
        "series_id": spec.series_id,
        "latest_observed_price": estimate,
        "latest_observation_date": latest_date.isoformat(),
        "next_session_estimate": estimate,
        "estimated_absolute_change": 0.0,
        "estimated_percentage_change": 0.0,
        "target_session": target_session,
        "next_session": target_session,
        "next_session_known": next_session_known,
        "next_session_status": next_session_status,
        "method": "naive_last_value",
        "estimate_kind": "baseline_estimate",
        "model_status": metrics["model_status"],
        "baseline_mae": metrics["baseline_mae"],
        "tested_ml_model": "RandomForestRegressor",
        "tested_ml_mae": metrics["tested_ml_mae"],
        "ml_used_for_estimate": False,
        "unit": point["unit"],
        "official": False,
        "data_status": meta["data_status"],
        "data_usage": meta.get("data_usage"),
        "price_type": meta.get("price_type"),
        "indicative": meta.get("indicative"),
        "experimental": meta.get("experimental"),
        "guaranteed_transaction_price": meta.get("guaranteed_transaction_price"),
        "provenance": meta.get("provenance"),
        "note": (
            "Naive last-value baseline. RandomForestRegressor was evaluated and did not "
            "beat this baseline. This is not an ML prediction."
        ),
    }
