"""Shared helpers for the whole project: config, AQI constants, feature recipe, run history.

One file on purpose: the same definitions are used by the pipeline (training) and the
backend (serving), which avoids training/serving skew.
"""
import json
import logging
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

POLLUTANTS = ["PM2.5", "PM10", "NO2", "SO2", "CO", "O3"]
CLASSES = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]

# CPCB breakpoints: (conc_lo, conc_hi, aqi_lo, aqi_hi). CO in mg/m3, others ug/m3.
BREAKPOINTS = {
    "PM2.5": [(0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200),
              (90, 120, 201, 300), (120, 250, 301, 400), (250, 500, 401, 500)],
    "PM10": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 250, 101, 200),
             (250, 350, 201, 300), (350, 430, 301, 400), (430, 600, 401, 500)],
    "NO2": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 180, 101, 200),
            (180, 280, 201, 300), (280, 400, 301, 400), (400, 800, 401, 500)],
    "SO2": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 380, 101, 200),
            (380, 800, 201, 300), (800, 1600, 301, 400), (1600, 2400, 401, 500)],
    "CO": [(0, 1, 0, 50), (1, 2, 51, 100), (2, 10, 101, 200),
           (10, 17, 201, 300), (17, 34, 301, 400), (34, 50, 401, 500)],
    "O3": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 168, 101, 200),
           (168, 208, 201, 300), (208, 748, 301, 400), (748, 1000, 401, 500)],
}


def load_params(path: str = "params.yaml") -> dict:
    """Load the YAML parameter file."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_logger(name: str) -> logging.Logger:
    """Return a consistently formatted logger."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    return logging.getLogger(name)


def ensure_dir(path: str) -> Path:
    """Create a directory if missing and return it."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- features
ENGINEERED = ["month", "pm_ratio", "nox_so2"]
FEATURES = POLLUTANTS + ENGINEERED


def add_engineered(df: pd.DataFrame, month: pd.Series) -> pd.DataFrame:
    """Add month, PM2.5/PM10 ratio and NO2/SO2 ratio columns to `df` (in place copy)."""
    out = df.copy()
    out["month"] = month.values if hasattr(month, "values") else month
    out["pm_ratio"] = out["PM2.5"] / (out["PM10"] + 1e-6)
    out["nox_so2"] = out["NO2"] / (out["SO2"] + 1e-6)
    return out


# ------------------------------------------------------------- run history
# Every pipeline stage appends a success/failure record; feeds the Pipeline console in the UI.
HISTORY = Path("metrics/run_history.jsonl")


@contextmanager
def track_stage(name: str):
    """Context manager: time a stage and record its outcome, re-raising errors."""
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    record = {"stage": name, "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        yield
        record["status"] = "success"
    except Exception as exc:  # noqa: BLE001 - we log then re-raise
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()[-800:]
        raise
    finally:
        record["seconds"] = round(time.time() - start, 3)
        with open(HISTORY, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
