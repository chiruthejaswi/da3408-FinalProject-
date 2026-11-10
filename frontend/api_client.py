"""Thin REST client. The ONLY place the UI touches the backend (loose coupling)."""
import os
import time
from typing import Optional

import requests

import ui_metrics


class ApiUnavailable(Exception):
    """Backend unreachable or timed out."""


class ApiError(Exception):
    """Backend replied with an error status."""

    def __init__(self, status: int, message: str, details: Optional[list] = None):
        super().__init__(message)
        self.status, self.message, self.details = status, message, details or []


class ApiClient:
    """Configurable (API_URL env var) client for the AirSense backend."""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        self.base_url = (base_url or os.getenv("API_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, **kw):
        start = time.perf_counter()
        try:
            resp = requests.request(method, f"{self.base_url}{path}",
                                    timeout=kw.pop("timeout", self.timeout), **kw)
        except requests.RequestException as exc:
            ui_metrics.API_CALLS.labels(path, "unavailable").inc()
            raise ApiUnavailable("The prediction service is not reachable right now.") from exc
        finally:
            ui_metrics.API_LATENCY.labels(path).observe(time.perf_counter() - start)
        if resp.status_code >= 400:
            ui_metrics.API_CALLS.labels(path, f"http_{resp.status_code}").inc()
            try:
                body = resp.json()
            except ValueError:
                body = {}
            raise ApiError(resp.status_code, body.get("message", f"Service error ({resp.status_code})"),
                           body.get("details"))
        ui_metrics.API_CALLS.labels(path, "ok").inc()
        return resp

    def health(self) -> dict:
        return self._request("GET", "/health", timeout=3).json()

    def cities(self) -> list:
        return self._request("GET", "/cities").json()["cities"]

    def predict(self, payload: dict) -> dict:
        return self._request("POST", "/predict", json=payload).json()

    def predict_batch(self, filename: str, content: bytes) -> dict:
        files = {"file": (filename, content, "text/csv")}
        return self._request("POST", "/predict/batch", files=files, timeout=60).json()

    def template_csv(self) -> str:
        return self._request("GET", "/template.csv").text

    def model_info(self) -> dict:
        return self._request("GET", "/model/info").json()

    def pipeline_status(self) -> dict:
        return self._request("GET", "/pipeline/status", timeout=30).json()
