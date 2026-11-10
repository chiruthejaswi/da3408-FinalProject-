"""Acceptance criteria tests (AC-1 .. AC-7). See docs/TEST_PLAN.md section 6 for the original vs revised criteria."""
import json
import time

import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from common import CLASSES, FEATURES, POLLUTANTS
from ingest import bucket, sub_index


def _formula_baseline():
    """Plain CPCB formula applied to the (imputed) test inputs: the rule the ML model must not be worse than."""
    test = pd.read_csv("data/processed/test.csv")
    aqi = test[POLLUTANTS].apply(lambda col: col.map(lambda v, p=col.name: sub_index(p, v))).max(axis=1)
    idx = {c: i for i, c in enumerate(CLASSES)}
    return test["label"], aqi.map(bucket).map(idx).fillna(0).astype(int)


def test_ac1_macro_f1_not_worse_than_formula_baseline():
    """AC-1 (revised): held-out macro-F1 >= the plain CPCB-formula baseline on the same inputs."""
    y, formula = _formula_baseline()
    base = float(f1_score(y, formula, average="macro", labels=range(6), zero_division=0))
    model_f1 = json.load(open("metrics/train_metrics.json"))["macro_f1"]
    json.dump({"baseline_macro_f1": round(base, 4), "baseline_accuracy": round(float((y == formula).mean()), 4),
               "model_macro_f1": model_f1, "rows": int(len(y))}, open("metrics/baseline.json", "w"), indent=2)
    assert model_f1 >= base


def test_ac2_health_critical_classes_recall_at_least_070():
    """AC-2 (revised): recall >= 0.70 for the health-critical classes Poor, Very Poor and Severe."""
    m = json.load(open("metrics/train_metrics.json"))
    assert min(m["recall_Poor"], m["recall_Very_Poor"], m["recall_Severe"]) >= 0.70


def test_ac3_p95_latency_under_300ms(client, valid_payload):
    """AC-3: p95 /predict latency < 300 ms over 100 requests."""
    times = []
    for _ in range(100):
        t = time.perf_counter()
        assert client.post("/predict", json=valid_payload).status_code == 200
        times.append((time.perf_counter() - t) * 1000)
    p95 = float(np.percentile(times, 95))
    json.dump({"requests": len(times), "p50_ms": round(float(np.percentile(times, 50)), 2),
               "p95_ms": round(p95, 2), "max_ms": round(max(times), 2)},
              open("metrics/latency.json", "w"), indent=2)
    assert p95 < 300


def test_ac4_model_matches_training_feature_set(client):
    """AC-4: serving feature list equals the training feature list."""
    assert client.get("/model/info").json()["features"] == FEATURES


def test_ac5_no_5xx_on_garbage_inputs(client):
    """AC-5: fuzzed bodies never produce a 5xx."""
    bad = [{}, {"city": 5}, {"city": "Delhi", "pm25": None, "pm10": None},
           {"city": "Delhi", "pm25": [1], "pm10": 2}, {"city": "", "pm25": 1, "pm10": 2}]
    assert all(client.post("/predict", json=b).status_code < 500 for b in bad)


def test_ac7_predictions_within_one_category():
    """AC-7: at least 95 % of held-out predictions are the right category or its direct neighbour."""
    test = pd.read_csv("data/processed/test.csv")
    test["month"] = test["month"].astype(float)
    pred = mlflow.sklearn.load_model("models/airsense_model").predict(test[FEATURES])
    exact, within = float((pred == test["label"]).mean()), float((abs(pred - test["label"]) <= 1).mean())
    json.dump({"exact": round(exact, 4), "within_one": round(within, 4)}, open("metrics/adjacent_accuracy.json", "w"), indent=2)
    assert within >= 0.95
