"""Prediction logic: domain errors, health advice lookup, and the model-backed Predictor."""
import json
import logging
from datetime import date as date_cls
from typing import List

import mlflow.sklearn
import numpy as np
import pandas as pd

from backend import metrics
from backend.schemas import POLLUTANT_FIELDS, Prediction
from common import FEATURES, add_engineered

# ------------------------------------------------------------------ errors
class AirSenseError(Exception):
    """Base class for expected, user-facing errors."""
    status_code = 400
    error = "bad_request"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnknownCityError(AirSenseError):
    """City is not one the model was trained on."""
    status_code = 422
    error = "unknown_city"


class InvalidInputError(AirSenseError):
    """Input failed a business-rule check."""
    status_code = 422
    error = "invalid_input"


class BatchFileError(AirSenseError):
    """Uploaded CSV is unreadable, too large, or has the wrong columns."""
    status_code = 400
    error = "invalid_file"


class ModelNotLoadedError(AirSenseError):
    """Model artefacts are missing or failed to load."""
    status_code = 503
    error = "model_unavailable"


# ------------------------------------------------------------------ advice
class HealthAdvisor:
    """Maps an AQI category to health guidance (config-driven, no code change needed)."""

    def __init__(self, path: str):
        with open(path, encoding="utf-8") as fh:
            self._table = json.load(fh)

    def for_category(self, category: str) -> dict:
        """Return colour/headline/advice for `category` (safe default if unknown)."""
        return self._table.get(category, {
            "color": "#808080", "headline": category,
            "advice": "No guidance available.", "sensitive": ""})


# --------------------------------------------------------------- predictor
log = logging.getLogger("predictor")
LOW_CONFIDENCE = 0.60


class Predictor:
    """Wraps model + metadata. Stateless per request, thread-safe for reads."""

    def __init__(self, model_dir: str, meta_path: str, advisor: HealthAdvisor):
        self.advisor = advisor
        try:
            with open(meta_path, encoding="utf-8") as fh:
                self.meta = json.load(fh)
            self.model = mlflow.sklearn.load_model(model_dir)
        except Exception as exc:  # noqa: BLE001
            log.exception("Model load failed")
            raise ModelNotLoadedError(f"Could not load model: {exc}") from exc
        # Serve single rows per request: avoid per-request thread pools oversubscribing the CPU.
        if hasattr(self.model, "n_jobs"):
            self.model.n_jobs = 1
        self.cities = set(self.meta["cities"])
        self.class_names = self.meta["classes"]
        metrics.MODEL_LOADED.set(1)
        metrics.MODEL_INFO.labels(self.meta["model_name"], self.meta["mlflow_run_id"],
                                  self.meta["git_commit"][:12]).set(1)
        log.info("Model loaded: %s (run %s)", self.meta["model_name"], self.meta["mlflow_run_id"])

    # ------------------------------------------------------------------
    def _row_to_frame(self, row: dict) -> tuple:
        """Validate one row dict -> (feature DataFrame, imputed field names)."""
        city = row["city"]
        if city not in self.cities:
            raise UnknownCityError(f"City '{city}' is not supported. "
                                   f"Choose one of: {', '.join(sorted(self.cities))}.")
        values, imputed, user_vals = {}, [], {}
        for field, (col, _) in POLLUTANT_FIELDS.items():
            val = row.get(field)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                med = self.meta["medians"][col]
                val = med.get(city, med["__global__"])
                imputed.append(col)
            else:
                user_vals[col] = float(val)
            values[col] = min(float(val), self.meta["caps"][col] * 5)  # soft cap, extreme only
        if len(user_vals) < 2:
            raise InvalidInputError("At least 2 pollutant readings are required.")
        month = (row.get("date") or date_cls.today()).month
        frame = add_engineered(pd.DataFrame([values]), pd.Series([float(month)]))
        frame["month"] = frame["month"].astype("float64")
        metrics.observe_inputs(user_vals, self.meta["feature_mean"], self.meta["feature_std"])
        return frame[FEATURES], imputed

    def predict_many(self, rows: List[dict]) -> List[Prediction]:
        """Predict a list of already-validated row dicts (raises on first bad row)."""
        frames, imputed_all = zip(*(self._row_to_frame(r) for r in rows))
        proba = self.model.predict_proba(pd.concat(frames, ignore_index=True))
        out = []
        for row, p, imputed in zip(rows, proba, imputed_all):
            full = np.zeros(len(self.class_names))
            for cls_idx, prob in zip(self.model.classes_, p):
                full[int(cls_idx)] = prob
            top = int(full.argmax())
            cat = self.class_names[top]
            info = self.advisor.for_category(cat)
            conf = float(full[top])
            metrics.PREDICTIONS.labels(cat).inc()
            metrics.CONFIDENCE.observe(conf)
            out.append(Prediction(
                city=row["city"], category=cat, confidence=round(conf, 4),
                probabilities={c: round(float(v), 4) for c, v in zip(self.class_names, full)},
                color=info["color"], headline=info["headline"], advice=info["advice"],
                sensitive_groups=info["sensitive"], imputed_fields=imputed,
                low_confidence=conf < LOW_CONFIDENCE))
        return out

    def predict_one(self, row: dict) -> Prediction:
        """Predict a single row dict."""
        return self.predict_many([row])[0]

    def info(self) -> dict:
        """Model metadata for /model/info."""
        keys = ["model_name", "mlflow_run_id", "git_commit", "dataset_md5", "trained_at",
                "data_source", "classes", "features", "cities", "test_metrics",
                "candidate_val_macro_f1"]
        return {k: self.meta.get(k) for k in keys}
