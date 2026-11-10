"""Prometheus instrumentation for the frontend (served on its own port)."""
import os
import threading

from prometheus_client import Counter, Histogram, start_http_server

PAGE_VIEWS = Counter("airsense_ui_page_views_total", "Page renders", ["page"])
PREDICT_CLICKS = Counter("airsense_ui_predict_total", "Predict button outcomes", ["outcome"])
BATCH_UPLOADS = Counter("airsense_ui_batch_total", "Batch upload outcomes", ["outcome"])
API_CALLS = Counter("airsense_ui_api_calls_total", "Backend calls from the UI",
                    ["endpoint", "outcome"])
API_LATENCY = Histogram("airsense_ui_api_seconds", "Backend latency seen by the UI",
                        ["endpoint"], buckets=(.05, .1, .25, .5, 1, 2.5, 5, 10, 30))

_started = False
_lock = threading.Lock()


def start_metrics_server() -> None:
    """Start the /metrics HTTP server once per process (idempotent)."""
    global _started
    with _lock:
        if _started:
            return
        port = int(os.getenv("UI_METRICS_PORT", "8001"))
        try:
            start_http_server(port)
        except OSError:  # port already bound (e.g. test runs)
            pass
        _started = True
