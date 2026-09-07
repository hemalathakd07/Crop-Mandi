"""Chronological walk-forward validation. Never shuffle time-series rows."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from sklearn.base import clone

from ml.baselines import mae, moving_average_from_features, naive_from_features, rmse
from ml.sessions import chronological_split_index


def assert_chronological(train_end: int, n: int) -> None:
    if not 0 < train_end < n:
        raise ValueError("train_end must leave a non-empty past and a non-empty future")


def expanding_walk_forward_predict(
    estimator,
    X: np.ndarray,
    y: np.ndarray,
    *,
    min_train: int,
    refit_every: int,
) -> np.ndarray:
    """
    For each t >= min_train, predict y[t] using only X[:t], y[:t].

    The estimator is cloned and refit every refit_every steps to keep runtime bounded.
    Predictions before min_train are NaN and must be excluded from metrics.
    """
    n = len(y)
    if min_train < 1 or min_train >= n:
        raise ValueError("min_train must leave at least one evaluation point")
    if refit_every < 1:
        raise ValueError("refit_every must be >= 1")
    preds = np.full(n, np.nan, dtype=float)
    model = None
    last_fit_at = -10**9
    for t in range(min_train, n):
        if model is None or (t - last_fit_at) >= refit_every:
            model = clone(estimator)
            model.fit(X[:t], y[:t])
            last_fit_at = t
        preds[t] = float(model.predict(X[t : t + 1])[0])
    return preds


def walk_forward_metrics(
    estimator_factory: Callable[[], object],
    X: np.ndarray,
    y: np.ndarray,
    *,
    min_train: int | None = None,
    refit_every: int | None = None,
) -> dict:
    n = len(y)
    if n < 4:
        raise ValueError("not enough supervised rows for walk-forward validation")
    origin = min_train if min_train is not None else chronological_split_index(n, 0.5)
    origin = max(2, min(n - 1, origin))
    step = refit_every if refit_every is not None else max(5, (n - origin) // 15 or 1)
    ml_all = expanding_walk_forward_predict(
        estimator_factory(),
        X,
        y,
        min_train=origin,
        refit_every=step,
    )
    mask = ~np.isnan(ml_all)
    y_eval = y[mask]
    ml_eval = ml_all[mask]
    naive_eval = naive_from_features(X)[mask]
    ma5_eval = moving_average_from_features(X, window=5)[mask]
    ma7_eval = moving_average_from_features(X, window=7)[mask]

    naive_mae = mae(y_eval, naive_eval)
    ma5_mae = mae(y_eval, ma5_eval)
    ma7_mae = mae(y_eval, ma7_eval)
    ml_mae = mae(y_eval, ml_eval)
    naive_rmse = rmse(y_eval, naive_eval)
    ma5_rmse = rmse(y_eval, ma5_eval)
    ml_rmse = rmse(y_eval, ml_eval)

    baseline_mae = naive_mae
    baseline_rmse = naive_rmse
    baseline_name = "naive_last_value"
    if ma5_mae < baseline_mae:
        baseline_mae = ma5_mae
        baseline_rmse = ma5_rmse
        baseline_name = "moving_average_5"
    if ma7_mae < baseline_mae:
        baseline_mae = ma7_mae
        baseline_rmse = rmse(y_eval, ma7_eval)
        baseline_name = "moving_average_7"

    improvement_vs_naive_pct = None
    if naive_mae > 0:
        improvement_vs_naive_pct = (naive_mae - ml_mae) / naive_mae * 100.0

    if ml_mae < naive_mae:
        model_status = "ML_BETTER_THAN_BASELINE"
    else:
        model_status = "BASELINE_BETTER"

    methods = {
        "naive_last_value": naive_mae,
        "moving_average_5": ma5_mae,
        "moving_average_7": ma7_mae,
        "random_forest": ml_mae,
    }
    best_method = min(methods, key=methods.get)

    return {
        "n_supervised": n,
        "training_observations": origin,
        "validation_observations": int(mask.sum()),
        "walk_forward_origin": origin,
        "refit_every": step,
        "naive_mae": naive_mae,
        "naive_rmse": naive_rmse,
        "ma5_mae": ma5_mae,
        "ma5_rmse": ma5_rmse,
        "ma7_mae": ma7_mae,
        "ma7_rmse": rmse(y_eval, ma7_eval),
        "ml_mae": ml_mae,
        "ml_rmse": ml_rmse,
        "baseline_mae": baseline_mae,
        "baseline_rmse": baseline_rmse,
        "best_baseline": baseline_name,
        "improvement_vs_naive_pct": improvement_vs_naive_pct,
        "model_status": model_status,
        "best_method": best_method,
        "methods_mae": methods,
    }
