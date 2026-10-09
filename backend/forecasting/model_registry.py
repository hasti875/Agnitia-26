"""
model_registry.py
=================
Model selection and versioning for the Climate Risk Arbitrage Engine.

This module provides a unified interface for loading the correct model
(synthetic or real-data) and reporting which model is active.

MODEL HIERARCHY
---------------
1. real_data_model.pkl   — trained on real-world data (preferred)
2. flood_risk_model.pkl  — trained on synthetic data (fallback)

The API uses this registry to determine which model to load and to
include model provenance information in every response.

The synthetic model is NEVER overwritten. The real-data model is
stored in a separate file and must pass validation before it can
be selected.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import joblib


class ModelType(str, Enum):
    SYNTHETIC = "synthetic_baseline"
    REAL_DATA = "real_data_model"


@dataclass
class ModelInfo:
    """Metadata about a loaded model."""
    model_type: ModelType
    model_path: str
    metadata_path: str
    metadata: dict
    is_available: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "model_type": self.model_type.value,
            "model_path": self.model_path,
            "is_available": self.is_available,
            "error": self.error,
            "trained_at_utc": self.metadata.get("trained_at_utc"),
            "forecast_horizon_hours": self.metadata.get("forecast_horizon_hours"),
            "source_data": self.metadata.get("source_data"),
            "disclaimer": self.metadata.get("disclaimer"),
            "test_metrics": self.metadata.get("test_metrics") or self.metadata.get("metrics"),
        }


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "forecasting", "models",
)

SYNTHETIC_MODEL_PATH = os.path.join(_MODELS_DIR, "flood_risk_model.pkl")
SYNTHETIC_METADATA_PATH = os.path.join(_MODELS_DIR, "model_metadata.json")

REAL_MODEL_PATH = os.path.join(_MODELS_DIR, "real_data_model.pkl")
REAL_METADATA_PATH = os.path.join(_MODELS_DIR, "real_data_metadata.json")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ModelRegistry:
    """
    Registry for managing model selection and provenance.

    Usage:
        registry = ModelRegistry()
        model, info = registry.get_active_model()
        # info.model_type tells you which model is active
    """

    def __init__(self) -> None:
        self._cache: Dict[ModelType, ModelInfo] = {}

    def _load_model_info(
        self,
        model_type: ModelType,
        model_path: str,
        metadata_path: str,
    ) -> ModelInfo:
        """Load model file and metadata, returning a ModelInfo."""
        if model_type in self._cache:
            return self._cache[model_type]

        if not os.path.exists(model_path):
            info = ModelInfo(
                model_type=model_type,
                model_path=model_path,
                metadata_path=metadata_path,
                metadata={},
                is_available=False,
                error=f"Model file not found: {model_path}",
            )
        elif not os.path.exists(metadata_path):
            info = ModelInfo(
                model_type=model_type,
                model_path=model_path,
                metadata_path=metadata_path,
                metadata={},
                is_available=False,
                error=f"Metadata file not found: {metadata_path}",
            )
        else:
            try:
                with open(metadata_path, "r", encoding="utf-8") as fh:
                    metadata = json.load(fh)
                info = ModelInfo(
                    model_type=model_type,
                    model_path=model_path,
                    metadata_path=metadata_path,
                    metadata=metadata,
                    is_available=True,
                )
            except Exception as e:
                info = ModelInfo(
                    model_type=model_type,
                    model_path=model_path,
                    metadata_path=metadata_path,
                    metadata={},
                    is_available=False,
                    error=f"Failed to load model: {e}",
                )

        self._cache[model_type] = info
        return info

    def get_synthetic_model(self) -> ModelInfo:
        """Get the synthetic baseline model info."""
        return self._load_model_info(
            ModelType.SYNTHETIC,
            SYNTHETIC_MODEL_PATH,
            SYNTHETIC_METADATA_PATH,
        )

    def get_real_model(self) -> ModelInfo:
        """Get the real-data model info."""
        return self._load_model_info(
            ModelType.REAL_DATA,
            REAL_MODEL_PATH,
            REAL_METADATA_PATH,
        )

    def get_active_model(self) -> tuple:
        """
        Get the active model (real-data if available, else synthetic).

        Returns
        -------
        (model_object, ModelInfo)

        The model object is a fitted sklearn estimator ready for .predict().
        """
        # Prefer real-data model if available
        real_info = self.get_real_model()
        if real_info.is_available:
            model = joblib.load(real_info.model_path)
            return model, real_info

        # Fall back to synthetic
        synth_info = self.get_synthetic_model()
        if synth_info.is_available:
            model = joblib.load(synth_info.model_path)
            return model, synth_info

        raise FileNotFoundError(
            "No available model found. Both synthetic and real-data "
            "models are missing or corrupted."
        )

    def get_model_status(self) -> dict:
        """
        Get a status report for both models.

        Returns a dict suitable for API responses:
        {
            "active_model": "synthetic_baseline" | "real_data_model",
            "models": {
                "synthetic_baseline": {...},
                "real_data_model": {...}
            },
            "warning": "..." (if real-data model is not available)
        }
        """
        synth_info = self.get_synthetic_model()
        real_info = self.get_real_model()

        if real_info.is_available:
            active = ModelType.REAL_DATA
            warning = None
        elif synth_info.is_available:
            active = ModelType.SYNTHETIC
            warning = (
                "Real-data model is not available. "
                "Using synthetic baseline model. "
                "Predictions are for demonstration only."
            )
        else:
            active = None
            warning = "No model available. Please train a model first."

        return {
            "active_model": active.value if active else None,
            "models": {
                ModelType.SYNTHETIC.value: synth_info.to_dict(),
                ModelType.REAL_DATA.value: real_info.to_dict(),
            },
            "warning": warning,
        }

    def invalidate_cache(self) -> None:
        """Clear the model cache (call after retraining)."""
        self._cache.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[ModelRegistry] = None


def get_registry() -> ModelRegistry:
    """Get the global model registry singleton."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
