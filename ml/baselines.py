"""Naive last-value and moving-average baselines. No future prices."""

from __future__ import annotations

import numpy as np

from ml.features import FEATURE_NAMES


def naive_from_features(X: np.ndarray) -> np.ndarray:
    """Last-value baseline: next session = latest previous price (lag_1)."""
    col = FEATURE_NAMES.index("lag_1")
    return np.asarray(X[:, col], dtype=float)


def moving_average_from_features(X: np.ndarray, window: int = 5) -> np.ndarray:
    """Moving-average baseline using the rolling mean already computed on past sessions."""
    if window == 3:
        name = "rolling_mean_3"
    elif window == 5:
        name = "rolling_mean_5"
    elif window == 7:
        name = "rolling_mean_7"
    else:
        raise ValueError("window must be 3, 5, or 7")
    col = FEATURE_NAMES.index(name)
    return np.asarray(X[:, col], dtype=float)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
