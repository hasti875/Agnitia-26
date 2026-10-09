"""
forecasting package — Phase 4 ML flood-risk forecast (6 hours ahead).

Training is OFFLINE (``backend.forecasting.train``) and produces:
    models/flood_risk_model.pkl      frozen RandomForestRegressor
    models/model_metadata.json       features, horizon, split, metrics

Inference (``backend.forecasting.predict``) only LOADS those artifacts —
it never retrains. The Phase 3 rule-based risk engine stays independent.
"""

from .features import (
    FEATURE_COLUMNS,
    FORECAST_HORIZON_HOURS,
    METADATA_PATH,
    MODEL_PATH,
    TARGET_COLUMN,
    build_feature_frame,
    latest_feature_rows,
    split_chronological,
)

__all__ = [
    "FEATURE_COLUMNS",
    "FORECAST_HORIZON_HOURS",
    "METADATA_PATH",
    "MODEL_PATH",
    "TARGET_COLUMN",
    "build_feature_frame",
    "latest_feature_rows",
    "split_chronological",
]
