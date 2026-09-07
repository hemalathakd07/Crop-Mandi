"""Run experimental next-session models. Does not ingest Coffee into production."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from cropmandi.config import ROOT
from ml.baselines import naive_from_features
from ml.datasets import (
    load_coffee_workbook,
    load_pepper_from_db,
    load_rice_from_db,
    write_experimental_coffee_frames,
)
from ml.features import FEATURE_NAMES, MAX_LAG, build_supervised
from ml.predict import build_prediction
from ml.registry import MIN_RAW_OBSERVATIONS, MIN_SUPERVISED_ROWS, PriceSeries
from ml.train import make_random_forest
from ml.validation import walk_forward_metrics

EXPERIMENT_DIR = ROOT / "ml" / "experiments"
ARTIFACT_DIR = ROOT / "ml" / "artifacts"


def _json_ready(value):
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def evaluate_series(series: PriceSeries) -> dict:
    X, y, _targets, _known, _idx = build_supervised(
        series.dates,
        series.prices,
        use_target_session_calendar=series.use_target_session_calendar,
    )
    n_raw = len(series.prices)
    n_sup = int(len(y))
    result = {
        "series_id": series.series_id,
        "display_name": series.display_name,
        "commodity": series.commodity,
        "unit": series.unit,
        "observations": n_raw,
        "supervised_rows": n_sup,
        "max_lag": MAX_LAG,
        "feature_names": list(FEATURE_NAMES),
        "provenance": series.provenance,
        "target_definition": series.provenance.get("target_rule"),
        "use_target_session_calendar": series.use_target_session_calendar,
    }
    if n_raw < MIN_RAW_OBSERVATIONS or n_sup < MIN_SUPERVISED_ROWS:
        result["evaluated"] = False
        result["unavailable_reason"] = "insufficient_historical_observations"
        result["prediction"] = build_prediction(
            series,
            model=None,
            model_used="none",
            baseline_mae=None,
            model_mae=None,
            model_status="UNAVAILABLE",
            n_supervised=n_sup,
        )
        return result

    metrics = walk_forward_metrics(make_random_forest, X, y)
    # Final model: fit on all supervised rows, then predict the next unpublished session.
    final_model = make_random_forest()
    final_model.fit(X, y)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_DIR / f"{series.series_id}.joblib"
    joblib.dump(
        {
            "model": final_model,
            "feature_names": list(FEATURE_NAMES),
            "series_id": series.series_id,
            "commodity": series.commodity,
        },
        artifact_path,
    )

    best = metrics["best_method"]
    if best == "random_forest":
        model_used = "random_forest"
        predict_model = final_model
    elif best == "naive_last_value":
        model_used = "naive_last_value"
        predict_model = _NaiveWrapper()
    elif best == "moving_average_5":
        model_used = "moving_average_5"
        predict_model = _MAWrapper(5)
    else:
        model_used = "moving_average_7"
        predict_model = _MAWrapper(7)

    prediction = build_prediction(
        series,
        model=predict_model,
        model_used=model_used,
        baseline_mae=metrics["naive_mae"],
        model_mae=metrics["ml_mae"],
        model_status=metrics["model_status"],
        n_supervised=n_sup,
    )
    result.update(metrics)
    result["evaluated"] = True
    result["artifact"] = str(artifact_path.relative_to(ROOT))
    result["prediction"] = prediction
    result["best_method"] = best
    return result


class _NaiveWrapper:
    def predict(self, X):
        return naive_from_features(np.asarray(X, dtype=float))


class _MAWrapper:
    def __init__(self, window: int):
        self.window = window

    def predict(self, X):
        from ml.baselines import moving_average_from_features

        return moving_average_from_features(np.asarray(X, dtype=float), window=self.window)


def run_experiment() -> dict:
    EXPERIMENT_DIR.mkdir(parents=True, exist_ok=True)
    coffee = load_coffee_workbook()
    write_experimental_coffee_frames(coffee)
    pepper = load_pepper_from_db()
    rice = load_rice_from_db()
    if set(pepper) & set(coffee):
        raise RuntimeError("Coffee and Pepper series ids collided")
    if set(rice) & set(coffee):
        raise RuntimeError("Coffee and Rice series ids collided")
    if set(rice) & set(pepper):
        raise RuntimeError("Pepper and Rice series ids collided")

    all_series = {**coffee, **pepper, **rice}
    evaluations = []
    for sid in [
        "coffee_arabica_parchment",
        "coffee_arabica_cherry",
        "coffee_robusta_parchment",
        "coffee_robusta_cherry",
        "pepper_cochin_garbled",
        "pepper_cochin_ungarbled",
        "pepper_sirsi",
        *sorted(rice),
    ]:
        series = all_series.get(sid)
        if series is None:
            evaluations.append(
                {
                    "series_id": sid,
                    "evaluated": False,
                    "unavailable_reason": "series_not_found",
                    "observations": 0,
                }
            )
            continue
        evaluations.append(evaluate_series(series))

    beat, failed, experimental_ready, production_ml_api, unavailable = [], [], [], [], []
    for row in evaluations:
        sid = row["series_id"]
        if not row.get("evaluated"):
            unavailable.append(sid)
            continue
        if row.get("model_status") == "ML_BETTER_THAN_BASELINE":
            beat.append(sid)
        else:
            failed.append(sid)
        pred = row.get("prediction") or {}
        if pred.get("available"):
            experimental_ready.append(sid)
            # Unverified coffee must not be wired as an official forecast API.
            if (
                row.get("commodity") == "pepper"
                and row.get("model_status") == "ML_BETTER_THAN_BASELINE"
            ):
                production_ml_api.append(sid)
        else:
            unavailable.append(sid)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment": "phase2_experimental_next_session_prices",
        "coffee_data_status": "UNVERIFIED_HISTORICAL_COFFEE_DATA",
        "coffee_data_usage": "EXPERIMENTAL_ONLY",
        "coffee_not_inserted_into_production_db": True,
        "original_excel_unmodified": True,
        "validation": "expanding_walk_forward_chronological",
        "random_split": False,
        "evaluations": evaluations,
        "which_models_beat_naive_baseline": beat,
        "which_models_failed_to_beat_naive_baseline": failed,
        "series_ready_for_experimental_prediction_payload": experimental_ready,
        "series_ready_for_prediction_api_integration": production_ml_api,
        "series_that_should_remain_unavailable": [
            sid
            for sid in [
                "coffee_arabica_parchment",
                "coffee_arabica_cherry",
                "coffee_robusta_parchment",
                "coffee_robusta_cherry",
            ]
            if sid not in unavailable
        ]
        + unavailable,
        "unavailable_reason_notes": {
            "coffee": (
                "Coffee series can emit an experimental payload, but they must remain "
                "unavailable for production/official prediction API integration because "
                "the source is UNVERIFIED_HISTORICAL_COFFEE_DATA and is experimental only."
            ),
            "ml_vs_baseline": (
                "No series beat the naive last-value baseline in walk-forward validation. "
                "Do not ship RandomForest as a superior model."
            ),
        },
        "notes": [
            "Coffee predictions are experimental only and are not Coffee Board forecasts.",
            "Pepper predictions use indicative daily averages, not guaranteed transaction prices.",
            "Rice predictions remain unavailable until an AGMARKNET market-variety series has enough historical observations.",
            "Coffee, Pepper, and Rice are never combined in one model.",
        ],
    }
    eval_path = EXPERIMENT_DIR / "evaluation_results.json"
    pred_path = EXPERIMENT_DIR / "prediction_output.json"
    cmp_path = EXPERIMENT_DIR / "model_comparison.json"
    meta_path = EXPERIMENT_DIR / "metadata.json"
    eval_path.write_text(json.dumps(_json_ready(report), indent=2), encoding="utf-8")
    pred_path.write_text(
        json.dumps(
            _json_ready([row.get("prediction") for row in evaluations]),
            indent=2,
        ),
        encoding="utf-8",
    )
    comparison = [
        {
            "series_id": row.get("series_id"),
            "display_name": row.get("display_name"),
            "observations": row.get("observations"),
            "training_observations": row.get("training_observations"),
            "validation_observations": row.get("validation_observations"),
            "naive_mae": row.get("naive_mae"),
            "ml_mae": row.get("ml_mae"),
            "naive_rmse": row.get("naive_rmse"),
            "ml_rmse": row.get("ml_rmse"),
            "improvement_vs_naive_pct": row.get("improvement_vs_naive_pct"),
            "best_method": row.get("best_method"),
            "model_status": row.get("model_status"),
        }
        for row in evaluations
    ]
    cmp_path.write_text(json.dumps(_json_ready(comparison), indent=2), encoding="utf-8")
    meta_path.write_text(
        json.dumps(
            {
                "coffee_data_status": "UNVERIFIED_HISTORICAL_COFFEE_DATA",
                "coffee_data_usage": "EXPERIMENTAL_ONLY",
                "pepper_price_type": "indicative_daily_average",
                "target": "next_published_available_market_session",
                "paths": {
                    "evaluation": str(eval_path.relative_to(ROOT)),
                    "predictions": str(pred_path.relative_to(ROOT)),
                    "comparison": str(cmp_path.relative_to(ROOT)),
                    "experimental_coffee_csv": "data/experimental/coffee_weekday_sessions.csv",
                    "artifacts": "ml/artifacts/",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report


def main() -> None:
    report = run_experiment()
    print(json.dumps(_json_ready({
        "wrote": "ml/experiments/",
        "beat_baseline": report["which_models_beat_naive_baseline"],
        "failed_baseline": report["which_models_failed_to_beat_naive_baseline"],
        "experimental_payloads": report["series_ready_for_experimental_prediction_payload"],
        "api_ready": report["series_ready_for_prediction_api_integration"],
        "unavailable": report["series_that_should_remain_unavailable"],
    }), indent=2))


if __name__ == "__main__":
    main()
