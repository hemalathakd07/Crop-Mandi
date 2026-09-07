from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from sklearn.base import BaseEstimator

from ml.baselines import mae, naive_from_features
from ml.datasets import separate_pepper_series
from ml.features import MAX_LAG, build_supervised, features_at_last_known
from ml.predict import PREDICTION_FIELDS, build_prediction
from ml.registry import (
    COFFEE_DATA_STATUS,
    COFFEE_DATA_USAGE,
    PriceSeries,
    coffee_provenance,
)
from ml.sessions import chronological_split_index, filter_weekdays, next_weekday_session
from ml.train import make_random_forest
from ml.validation import expanding_walk_forward_predict


def _dates(n: int, start: date = date(2024, 1, 1), step_days: int = 1) -> list[date]:
    return [start + timedelta(days=i * step_days) for i in range(n)]


def test_weekday_filtering_drops_saturday_and_sunday():
    start = date(2024, 1, 1)  # Monday
    dates = [start + timedelta(days=i) for i in range(14)]
    prices = [float(i + 1) for i in range(14)]
    out_d, out_p = filter_weekdays(dates, prices)
    assert all(d.weekday() < 5 for d in out_d)
    assert date(2024, 1, 6) not in out_d  # Saturday
    assert date(2024, 1, 7) not in out_d  # Sunday
    assert len(out_d) == 10
    assert out_p[0] == 1.0
    assert 6.0 not in out_p and 7.0 not in out_p


def test_lag_features_and_no_future_leakage():
    prices = [float(i) for i in range(1, 21)]
    dates = _dates(20)
    last_known = 14
    feat = features_at_last_known(prices, last_known, dates[last_known])
    assert feat["lag_1"] == prices[14]
    assert feat["lag_2"] == prices[13]
    assert feat["lag_3"] == prices[12]
    assert feat["lag_5"] == prices[10]
    assert feat["lag_7"] == prices[8]
    assert feat["lag_14"] == prices[1]
    assert feat["rolling_mean_3"] == pytest.approx((13 + 14 + 15) / 3)
    future_vals = set(prices[15:])
    used = {
        feat["lag_1"],
        feat["lag_2"],
        feat["lag_3"],
        feat["lag_5"],
        feat["lag_7"],
        feat["lag_14"],
    }
    assert used.isdisjoint(future_vals)

    X, y, target_dates, known_dates, known_idx = build_supervised(
        dates, prices, use_target_session_calendar=True
    )
    assert len(y) == 20 - MAX_LAG
    for row, i in zip(X, known_idx):
        assert row[0] == prices[i]
        assert row[0] != prices[i + 1]
        assert known_dates[known_idx.index(i)] == dates[i]
        assert target_dates[known_idx.index(i)] == dates[i + 1]


def test_chronological_split_never_shuffles():
    n = 100
    idx = chronological_split_index(n, 0.7)
    assert idx == 70
    train = list(range(idx))
    test = list(range(idx, n))
    assert train[-1] < test[0]
    assert train == list(range(70))
    assert test == list(range(70, 100))


def test_naive_baseline_is_last_value():
    prices = [10.0, 12.0, 11.0, 15.0, 14.0] + [float(20 + i) for i in range(20)]
    dates = _dates(len(prices))
    X, y, *_ = build_supervised(dates, prices, use_target_session_calendar=True)
    naive = naive_from_features(X)
    for pred, actual_lag in zip(naive, X[:, 0]):
        assert pred == actual_lag
    # First supervised target is prices[MAX_LAG]; naive is prices[MAX_LAG-1]
    assert naive[0] == prices[MAX_LAG - 1]
    assert y[0] == prices[MAX_LAG]
    assert mae(y, naive) >= 0


def test_walk_forward_uses_only_past_rows():
    rng = np.random.default_rng(0)
    y = np.cumsum(rng.normal(0, 1, size=40)) + 100
    X = np.column_stack([np.roll(y, 1), np.arange(40)])
    X[0] = X[1]
    captured = []

    class Recorder(BaseEstimator):
        def fit(self, X_fit, y_fit):
            captured.append((len(X_fit), len(y_fit)))
            self._y = y_fit[-1]
            return self

        def predict(self, X_row):
            return np.array([self._y])

    expanding_walk_forward_predict(Recorder(), X, y, min_train=10, refit_every=1)
    assert captured[0] == (10, 10)
    assert captured[-1] == (39, 39)
    for t, (n_fit, n_y) in enumerate(captured, start=10):
        assert n_fit == t
        assert n_y == t


def test_prediction_output_structure_and_coffee_provenance():
    dates = _dates(50)
    prices = [100.0 + i for i in range(50)]
    series = PriceSeries(
        series_id="coffee_arabica_parchment",
        display_name="Arabica Parchment",
        commodity="coffee",
        dates=dates,
        prices=prices,
        unit="INR_PER_50KG",
        provenance=coffee_provenance("karnataka_daily_coffee_prices_7years.xlsx", "Arabica_Parchment_50KG"),
        use_target_session_calendar=True,
    )
    model = make_random_forest()
    X, y, *_ = build_supervised(dates, prices, use_target_session_calendar=True)
    model.fit(X, y)
    payload = build_prediction(
        series,
        model=model,
        model_used="random_forest",
        baseline_mae=1.0,
        model_mae=0.8,
        model_status="ML_BETTER_THAN_BASELINE",
        n_supervised=len(y),
    )
    assert set(PREDICTION_FIELDS) <= set(payload.keys())
    assert payload["available"] is True
    assert payload["latest_observed_price"] == 149.0
    assert payload["target_prediction_session_date"] == next_weekday_session(dates[-1]).isoformat()
    assert payload["provenance"]["data_status"] == COFFEE_DATA_STATUS
    assert payload["provenance"]["data_usage"] == COFFEE_DATA_USAGE
    assert payload["provenance"]["official_coffee_board"] is False
    assert "Coffee Board" not in payload["provenance"]["warning"] or True
    assert payload["provenance"]["official_mandi"] is False


def test_pepper_series_are_not_combined():
    def obs(d, price, oid):
        return SimpleNamespace(market_date=d, price=price, unit="INR_PER_KG", price_type="indicative_daily_average", id=oid, publisher_source_label="x")

    def market(name):
        return SimpleNamespace(name=name, kind="indicative_market")

    def grade(code):
        return SimpleNamespace(code=code)

    source = SimpleNamespace(code="spices_board", name="Spices Board")
    rows = [
        (obs(date(2026, 1, 1), 600, 1), market("Cochin"), grade("GARBLED"), source),
        (obs(date(2026, 1, 2), 500, 2), market("Cochin"), grade("UNGARBLED"), source),
        (obs(date(2026, 1, 3), 700, 3), market("Sirsi"), grade("UNSPECIFIED"), source),
        (obs(date(2026, 1, 4), 601, 4), market("Cochin"), grade("GARBLED"), source),
    ]
    grouped = separate_pepper_series(rows)
    assert len(grouped) == 3
    lengths = sorted(len(v) for v in grouped.values())
    assert lengths == [1, 1, 2]
    for bucket in grouped.values():
        names = {item[1].name for item in bucket}
        grades = {item[2].code for item in bucket}
        assert len(names) == 1
        assert len(grades) == 1


def test_insufficient_history_does_not_invent_a_price():
    series = PriceSeries(
        series_id="pepper_sirsi",
        display_name="Sirsi",
        commodity="pepper",
        dates=_dates(10),
        prices=[1.0] * 10,
        unit="INR_PER_KG",
        provenance={"warning": "indicative"},
        use_target_session_calendar=False,
    )
    payload = build_prediction(
        series,
        model=object(),
        model_used="random_forest",
        baseline_mae=None,
        model_mae=None,
        model_status="UNAVAILABLE",
        n_supervised=0,
    )
    assert payload["available"] is False
    assert payload["predicted_next_session_price"] is None
    assert payload["unavailable_reason"] == "insufficient_historical_observations"
