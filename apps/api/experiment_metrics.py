"""Load cached Phase 2 walk-forward metrics. Does not retrain models."""

from __future__ import annotations

import json
from pathlib import Path

import apps.api.runtime as runtime


def load_comparison(path: Path | None = None) -> dict[str, dict]:
    target = path or runtime.EXPERIMENT_COMPARISON_PATH
    if not target.is_file():
        return {}
    raw = json.loads(target.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    if isinstance(raw, list):
        rows = raw
    else:
        rows = raw.get("evaluations", [])
    for row in rows:
        sid = row.get("series_id")
        if sid:
            out[sid] = row
    return out


def metrics_for(series_id: str) -> dict:
    row = load_comparison().get(series_id, {})
    return {
        "method": "naive_last_value",
        "estimate_kind": "baseline_estimate",
        "model_status": row.get("model_status") or "BASELINE_BETTER",
        "baseline_mae": row.get("naive_mae"),
        "tested_ml_model": "RandomForestRegressor",
        "tested_ml_mae": row.get("ml_mae"),
        "best_method": row.get("best_method") or "naive_last_value",
    }
