"""Lag and rolling features from information available at the last known session."""

from __future__ import annotations

from datetime import date

import numpy as np

FEATURE_NAMES = (
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_5",
    "lag_7",
    "lag_14",
    "rolling_mean_3",
    "rolling_mean_5",
    "rolling_mean_7",
    "rolling_std_7",
    "day_of_week",
    "month",
)

MAX_LAG = 14


def _window_mean(values: list[float], end_inclusive: int, width: int) -> float:
    start = end_inclusive - width + 1
    if start < 0:
        raise ValueError("window extends before the start of the series")
    chunk = values[start : end_inclusive + 1]
    return float(np.mean(chunk))


def _window_std(values: list[float], end_inclusive: int, width: int) -> float:
    start = end_inclusive - width + 1
    if start < 0:
        raise ValueError("window extends before the start of the series")
    chunk = values[start : end_inclusive + 1]
    return float(np.std(chunk, ddof=0))


def features_at_last_known(
    prices: list[float],
    last_known_idx: int,
    calendar_date: date,
) -> dict[str, float]:
    """
    Features describing the series through last_known_idx inclusive.

    lag_1 is the latest observed price. No price after last_known_idx is used.
    calendar_date is the session whose weekday/month are encoded (see datasets).
    """
    i = last_known_idx
    if i < MAX_LAG - 1:
        raise ValueError(f"need at least {MAX_LAG} observations through last_known_idx")
    p = prices
    return {
        "lag_1": float(p[i]),
        "lag_2": float(p[i - 1]),
        "lag_3": float(p[i - 2]),
        "lag_5": float(p[i - 4]),
        "lag_7": float(p[i - 6]),
        "lag_14": float(p[i - 13]),
        "rolling_mean_3": _window_mean(p, i, 3),
        "rolling_mean_5": _window_mean(p, i, 5),
        "rolling_mean_7": _window_mean(p, i, 7),
        "rolling_std_7": _window_std(p, i, 7),
        "day_of_week": float(calendar_date.weekday()),
        "month": float(calendar_date.month),
    }


def feature_vector(feat: dict[str, float]) -> np.ndarray:
    return np.array([feat[name] for name in FEATURE_NAMES], dtype=float)


def build_supervised(
    dates: list[date],
    prices: list[float],
    *,
    use_target_session_calendar: bool,
) -> tuple[np.ndarray, np.ndarray, list[date], list[date], list[int]]:
    """
    One row per next-session target.

    last_known index i predicts prices[i+1] (the next published session in this series).
    Calendar features:
      - Coffee (use_target_session_calendar=True): weekday/month of the target session,
        which is the next weekday and is known before that session.
      - Pepper (False): weekday/month of the last known session, because the next
        publication date is not known until that observation appears.
    """
    if len(dates) != len(prices):
        raise ValueError("dates and prices must be the same length")
    xs: list[np.ndarray] = []
    ys: list[float] = []
    target_dates: list[date] = []
    known_dates: list[date] = []
    known_indices: list[int] = []
    n = len(prices)
    for i in range(MAX_LAG - 1, n - 1):
        cal = dates[i + 1] if use_target_session_calendar else dates[i]
        feat = features_at_last_known(prices, i, cal)
        # Leakage guard: lag_1 must equal the last known price, not the target.
        if feat["lag_1"] != float(prices[i]):
            raise RuntimeError("lag_1 must equal the last known price")
        xs.append(feature_vector(feat))
        ys.append(float(prices[i + 1]))
        target_dates.append(dates[i + 1])
        known_dates.append(dates[i])
        known_indices.append(i)
    if not xs:
        return (
            np.empty((0, len(FEATURE_NAMES))),
            np.empty((0,)),
            [],
            [],
            [],
        )
    return np.vstack(xs), np.asarray(ys, dtype=float), target_dates, known_dates, known_indices
