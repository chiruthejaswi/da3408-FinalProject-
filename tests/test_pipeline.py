"""Unit tests for data/feature/run-log code (TC-01 .. TC-10)."""
import json

import numpy as np
import pandas as pd
import pytest

import common as runlog
from common import FEATURES, add_engineered
from ingest import bucket, make_synthetic, sub_index, validate


def test_tc01_sub_index_band_boundaries():
    """PM2.5 of 30 is the top of 'Good' (AQI 50); 60 is top of 'Satisfactory' (100)."""
    assert sub_index("PM2.5", 30) == pytest.approx(50)
    assert sub_index("PM2.5", 60) == pytest.approx(100)


def test_tc02_sub_index_missing_is_nan():
    """A missing reading gives NaN, not an exception."""
    assert np.isnan(sub_index("CO", np.nan))


@pytest.mark.parametrize("aqi,cat", [(25, "Good"), (75, "Satisfactory"), (150, "Moderate"),
                                     (250, "Poor"), (350, "Very Poor"), (450, "Severe")])
def test_tc03_bucket_mapping(aqi, cat):
    """Every CPCB band maps to the right category."""
    assert bucket(aqi) == cat


def test_tc04_synthetic_schema_and_classes():
    """Synthetic data has the required schema and all six classes."""
    df = make_synthetic(600, seed=1)
    assert {"City", "Date", "PM2.5", "AQI_Bucket"} <= set(df.columns)
    assert df["AQI_Bucket"].nunique() == 6


def test_tc05_validate_reports_quality():
    """validate() returns row/city counts and null percentages."""
    rep = validate(make_synthetic(100, seed=1))
    assert rep["rows"] == 1000 and rep["cities"] == 10 and "PM2.5" in rep["null_pct"]


def test_tc06_validate_rejects_missing_column():
    """A file without pollutant columns fails loudly."""
    with pytest.raises(ValueError, match="Missing required columns"):
        validate(pd.DataFrame({"City": ["Delhi"], "Date": ["2020-01-01"]}))


def test_tc07_validate_rejects_empty():
    """An empty dataset fails loudly."""
    cols = ["City", "Date", "PM2.5", "PM10", "NO2", "SO2", "CO", "O3", "AQI_Bucket"]
    with pytest.raises(ValueError, match="empty"):
        validate(pd.DataFrame(columns=cols))


def test_tc08_feature_engineering():
    """Ratios are computed and all model FEATURES exist."""
    df = pd.DataFrame([{"PM2.5": 50.0, "PM10": 100.0, "NO2": 40.0, "SO2": 10.0, "CO": 1.0, "O3": 30.0}])
    out = add_engineered(df, pd.Series([6.0]))
    assert out["pm_ratio"].iloc[0] == pytest.approx(0.5, rel=1e-3)
    assert out["nox_so2"].iloc[0] == pytest.approx(4.0, rel=1e-3)
    assert list(out[FEATURES].columns) == FEATURES


def test_tc09_runlog_records_success(tmp_path, monkeypatch):
    """track_stage appends a success record."""
    monkeypatch.setattr(runlog, "HISTORY", tmp_path / "h.jsonl")
    with runlog.track_stage("demo"):
        pass
    rec = json.loads((tmp_path / "h.jsonl").read_text().splitlines()[0])
    assert rec["stage"] == "demo" and rec["status"] == "success"


def test_tc10_runlog_records_failure_and_reraises(tmp_path, monkeypatch):
    """track_stage records failure details and re-raises the exception."""
    monkeypatch.setattr(runlog, "HISTORY", tmp_path / "h.jsonl")
    with pytest.raises(RuntimeError):
        with runlog.track_stage("boom"):
            raise RuntimeError("bad")
    rec = json.loads((tmp_path / "h.jsonl").read_text().splitlines()[0])
    assert rec["status"] == "failed" and "RuntimeError" in rec["error"]


# ---- Ray transform + training helpers (pure functions, testable without a Ray cluster) ----
def test_tc46_preprocess_transform_imputes_and_clips():
    """preprocess.make_transform fills blanks with city medians, nulls negatives and clips outliers."""
    from common import POLLUTANTS
    from preprocess import make_transform
    medians = {p: {"Delhi": 10.0, "__global__": 5.0} for p in POLLUTANTS}
    caps = {p: 100.0 for p in POLLUTANTS}
    df = pd.DataFrame([{"City": "Delhi", "Date": "2020-03-01", "AQI_Bucket": "Good",
                        "PM2.5": np.nan, "PM10": -4.0, "NO2": 999.0, "SO2": 1.0, "CO": 1.0, "O3": 1.0}])
    out = make_transform(medians, caps)(df).iloc[0]
    assert out["PM2.5"] == 10.0 and out["PM10"] == 10.0 and out["NO2"] == 100.0
    assert out["month"] == 3 and out["label"] == 0


def test_tc47_train_evaluate_returns_per_class_recall():
    """train.evaluate reports accuracy, macro-F1 and one recall per class."""
    from common import CLASSES
    from train import evaluate

    class Perfect:
        def predict(self, X):
            return X["y"].values
    X = pd.DataFrame({"y": [0, 1, 2, 3, 4, 5]})
    res = evaluate(Perfect(), X, X["y"])
    assert res["accuracy"] == 1.0 and res["macro_f1"] == 1.0
    assert sum(k.startswith("recall_") for k in res) == len(CLASSES)


def test_tc48_train_candidates_and_git_hash():
    """Three candidate models are defined; git_commit() always returns a string."""
    from common import load_params
    from train import build_models, git_commit
    assert set(build_models(load_params()["train"])) == {"logreg", "random_forest", "hist_gb"}
    assert isinstance(git_commit(), str)
