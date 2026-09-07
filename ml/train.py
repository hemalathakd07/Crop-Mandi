from __future__ import annotations

from sklearn.ensemble import RandomForestRegressor


def make_random_forest(random_state: int = 42) -> RandomForestRegressor:
    """Small robust tree model for the hackathon prototype."""
    return RandomForestRegressor(
        n_estimators=60,
        max_depth=8,
        min_samples_leaf=5,
        max_features="sqrt",
        random_state=random_state,
        n_jobs=1,
    )
