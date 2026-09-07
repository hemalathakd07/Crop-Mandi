"""Next-session prediction payload. No fabricated prices."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
from sklearn.base import BaseEstimator

from ml.features import MAX_LAG, feature_vector, features_at_last_known
from ml.registry import MIN_RAW_OBSERVATIONS, MIN_SUPERVISED_ROWS, PriceSeries
from ml.sessions import next_weekday_session


PREDICTION_FIELDS = (
    "series_id",
    "display_name",
    "commodity",
    "latest_observed_price",
    "latest_observed_date",
    "predicted_next_session_price",
    "predicted_absolute_change",
    "predicted_percentage_change",
    "target_prediction_session_date",
    "target_prediction_session_label",
    "model_used",
    "baseline_mae",
    "model_mae",
    "model_status",
    "available",
    "unavailable_reason",
    "unit",
    "provenance",
)


def next_session_features(series: PriceSeries) -> tuple[np.ndarray, date | None, str]:
    if len(series.prices) < MAX_LAG:
        raise ValueError("insufficient history for lag features")
    last_idx = len(series.prices) - 1
    last_date = series.dates[last_idx]
    if series.use_target_session_calendar:
        target_date = next_weekday_session(last_date)
        label = target_date.isoformat()
        cal = target_date
    else:
        target_date = None
        label = f"next_published_session_after_{last_date.isoformat()}"
        cal = last_date
    feat = features_at_last_known(series.prices, last_idx, cal)
    return feature_vector(feat), target_date, label


def build_prediction(
    series: PriceSeries,
    *,
    model: BaseEstimator | None,
    model_used: str,
    baseline_mae: float | None,
    model_mae: float | None,
    model_status: str,
    n_supervised: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {key: None for key in PREDICTION_FIELDS}
    payload["series_id"] = series.series_id
    payload["display_name"] = series.display_name
    payload["commodity"] = series.commodity
    payload["unit"] = series.unit
    payload["provenance"] = dict(series.provenance)
    payload["model_used"] = model_used
    payload["baseline_mae"] = baseline_mae
    payload["model_mae"] = model_mae
    payload["model_status"] = model_status

    if not series.dates:
        payload["available"] = False
        payload["unavailable_reason"] = "no_observations"
        return payload

    payload["latest_observed_price"] = float(series.prices[-1])
    payload["latest_observed_date"] = series.dates[-1].isoformat()

    if len(series.prices) < MIN_RAW_OBSERVATIONS or n_supervised < MIN_SUPERVISED_ROWS:
        payload["available"] = False
        payload["unavailable_reason"] = "insufficient_historical_observations"
        if series.use_target_session_calendar:
            nxt = next_weekday_session(series.dates[-1])
            payload["target_prediction_session_date"] = nxt.isoformat()
            payload["target_prediction_session_label"] = nxt.isoformat()
        else:
            payload["target_prediction_session_label"] = (
                f"next_published_session_after_{series.dates[-1].isoformat()}"
            )
        return payload

    if model is None:
        payload["available"] = False
        payload["unavailable_reason"] = "no_fitted_model"
        return payload

    x, target_date, label = next_session_features(series)
    yhat = float(model.predict(x.reshape(1, -1))[0])
    latest = float(series.prices[-1])
    payload["available"] = True
    payload["unavailable_reason"] = None
    payload["predicted_next_session_price"] = yhat
    payload["predicted_absolute_change"] = yhat - latest
    payload["predicted_percentage_change"] = (
        ((yhat - latest) / latest) * 100.0 if latest else None
    )
    payload["target_prediction_session_date"] = (
        target_date.isoformat() if target_date else None
    )
    payload["target_prediction_session_label"] = label
    return payload
