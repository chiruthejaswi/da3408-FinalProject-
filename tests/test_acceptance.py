"""Acceptance criteria tests (AC-1 .. AC-4)."""
import json
import time

import numpy as np

from common import FEATURES


def test_ac1_macro_f1_at_least_080():
    """AC-1: held-out (future) macro-F1 >= 0.80."""
    assert json.load(open("metrics/train_metrics.json"))["macro_f1"] >= 0.80


def test_ac2_every_class_recall_at_least_070():
    """AC-2: no class (incl. rare Severe) has recall below 0.70."""
    m = json.load(open("metrics/train_metrics.json"))
    assert min(v for k, v in m.items() if k.startswith("recall_")) >= 0.70


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
