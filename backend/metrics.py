"""Prometheus instrumentation for the backend."""
from collections import defaultdict, deque

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("airsense_http_requests_total", "HTTP requests",
                   ["method", "path", "status"])
LATENCY = Histogram("airsense_http_request_seconds", "HTTP request latency",
                    ["path"], buckets=(.01, .025, .05, .1, .25, .5, 1, 2.5, 5))
ERRORS = Counter("airsense_errors_total", "Errors by type", ["type"])
PREDICTIONS = Counter("airsense_predictions_total", "Predictions by category", ["category"])
BATCH_ROWS = Counter("airsense_batch_rows_total", "Rows processed in batch", ["outcome"])
CONFIDENCE = Histogram("airsense_prediction_confidence", "Top-class probability",
                       buckets=(.3, .4, .5, .6, .7, .8, .9, .95, .99, 1.0))
INPUT_VALUE = Histogram("airsense_input_value", "Pollutant values received",
                        ["feature"], buckets=(5, 10, 25, 50, 100, 150, 250, 400, 700, 1000))
DRIFT = Gauge("airsense_input_drift_zscore",
              "(rolling mean of recent inputs - training mean) / training std", ["feature"])
MODEL_INFO = Gauge("airsense_model_info", "Loaded model (value is always 1)",
                   ["model", "run_id", "git_commit"])
MODEL_LOADED = Gauge("airsense_model_loaded", "1 if the model is loaded")

_window = defaultdict(lambda: deque(maxlen=200))


def observe_inputs(values: dict, train_mean: dict, train_std: dict) -> None:
    """Record raw inputs (user-supplied only) and update rolling drift gauges."""
    for feat, val in values.items():
        INPUT_VALUE.labels(feat).observe(val)
        _window[feat].append(val)
        std = train_std.get(feat) or 1.0
        win = _window[feat]
        DRIFT.labels(feat).set((sum(win) / len(win) - train_mean.get(feat, 0.0)) / std)
