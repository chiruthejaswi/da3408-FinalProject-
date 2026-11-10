"""AirSense inference API (FastAPI). Independent of the UI; REST only."""
import io
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import ValidationError

from backend import config as settings
from backend import metrics
from backend.pipeline_status import build_status
from backend.predictor import AirSenseError, BatchFileError, HealthAdvisor, ModelNotLoadedError, Predictor
from backend.schemas import (POLLUTANT_FIELDS, BatchResponse, PredictRequest,
                                 Prediction, RowError)


def setup_logging(log_dir: str) -> None:
    """Configure root logger once (idempotent)."""
    root = logging.getLogger()
    if getattr(root, "_airsense_configured", False):
        return
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    try:
        os.makedirs(log_dir, exist_ok=True)
        fh = RotatingFileHandler(os.path.join(log_dir, "backend.log"),
                                 maxBytes=1_000_000, backupCount=3)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        root.warning("File logging disabled (cannot write to %s)", log_dir)
    root._airsense_configured = True


setup_logging(settings.LOG_DIR)
log = logging.getLogger("api")

_state = {"predictor": None}
COLUMN_TO_FIELD = {col: field for field, (col, _) in POLLUTANT_FIELDS.items()}
KNOWN_PATHS = {"/predict", "/predict/batch", "/health", "/metrics", "/model/info",
               "/pipeline/status", "/cities", "/template.csv"}


def get_predictor() -> Predictor:
    """Lazy-load the model once; raises ModelNotLoadedError (503) if unavailable."""
    if _state["predictor"] is None:
        _state["predictor"] = Predictor(settings.MODEL_DIR, settings.META_PATH,
                                        HealthAdvisor(settings.ADVICE_PATH))
    return _state["predictor"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load the model at startup; keep serving /health even if loading fails."""
    try:
        get_predictor()
    except ModelNotLoadedError as exc:
        log.error("Starting WITHOUT model: %s", exc.message)
    yield


app = FastAPI(title="AirSense API", version="1.0.0", lifespan=lifespan,
              description="Predict the Indian AQI category from pollutant readings.")


# ---------------------------------------------------------------- middleware
@app.middleware("http")
async def instrument(request: Request, call_next):
    """Count requests and record latency for every call."""
    path = request.url.path if request.url.path in KNOWN_PATHS else "other"
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - start
        metrics.REQUESTS.labels(request.method, path, str(status)).inc()
        metrics.LATENCY.labels(path).observe(elapsed)
        log.info("%s %s -> %s (%.1f ms)", request.method, request.url.path, status, elapsed * 1000)


# ------------------------------------------------------------ error handlers
@app.exception_handler(AirSenseError)
async def domain_error(_: Request, exc: AirSenseError):
    metrics.ERRORS.labels(exc.error).inc()
    log.warning("%s: %s", exc.error, exc.message)
    return JSONResponse(status_code=exc.status_code,
                        content={"error": exc.error, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    metrics.ERRORS.labels("validation").inc()
    details = [{"field": ".".join(str(p) for p in e["loc"][1:]) or "body",
                "message": e["msg"].replace("Value error, ", "")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "error": "validation_error", "message": "Some inputs are invalid.", "details": details})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    metrics.ERRORS.labels("unexpected").inc()
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={
        "error": "internal_error", "message": "Something went wrong. Please try again."})


# ------------------------------------------------------------------ endpoints
@app.get("/health")
def health():
    """Liveness + whether the model is loaded."""
    return {"status": "ok" if _state["predictor"] else "degraded",
            "model_loaded": _state["predictor"] is not None}


@app.get("/metrics")
def prometheus_metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/cities")
def cities():
    """Supported cities (drives the UI dropdown)."""
    return {"cities": sorted(get_predictor().cities)}


@app.get("/model/info")
def model_info():
    """Model version, training metrics and provenance."""
    return get_predictor().info()


@app.get("/pipeline/status")
def pipeline_status():
    """DVC DAG, stage run history, pipeline metrics and MLflow runs."""
    return build_status(settings)


@app.post("/predict", response_model=Prediction, responses={422: {"description": "Invalid input"}})
def predict(req: PredictRequest):
    """Predict AQI category for one city/reading set."""
    return get_predictor().predict_one(req.model_dump())


@app.get("/template.csv", response_class=PlainTextResponse)
def template():
    """Example CSV for batch upload."""
    return ("City,Date,PM2.5,PM10,NO2,SO2,CO,O3\n"
            "Delhi,2026-11-02,145,290,62,18,2.1,41\n"
            "Chennai,2026-11-02,32,70,24,11,0.8,30\n")


@app.post("/predict/batch", response_model=BatchResponse)
async def predict_batch(file: UploadFile = File(...)):
    """Predict many rows from an uploaded CSV. Bad rows are reported, not fatal."""
    raw = await file.read()
    if len(raw) > settings.MAX_UPLOAD_BYTES:
        raise BatchFileError("File is too large (limit 5 MB).")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise BatchFileError("Could not read the file as CSV.") from exc
    if "City" not in df.columns:
        raise BatchFileError("Missing required column 'City'.")
    if not any(c in df.columns for c in COLUMN_TO_FIELD):
        raise BatchFileError("No pollutant columns found. Expected: PM2.5, PM10, NO2, SO2, CO, O3.")
    if df.empty:
        raise BatchFileError("The file has no data rows.")
    if len(df) > settings.MAX_BATCH_ROWS:
        raise BatchFileError(f"Too many rows ({len(df)}). Limit is {settings.MAX_BATCH_ROWS}.")

    predictor, results, errors = get_predictor(), [], []
    for i, rec in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        try:
            payload = {"city": str(rec["City"]).strip(),
                       "date": pd.to_datetime(rec.get("Date")).date() if pd.notna(rec.get("Date")) else None}
            for col, field in COLUMN_TO_FIELD.items():
                v = rec.get(col)
                payload[field] = None if v is None or pd.isna(v) else float(v)
            req = PredictRequest(**payload)  # reuse the same validation as /predict
            pred = predictor.predict_one(req.model_dump())
            results.append({"row": i, **pred.model_dump(exclude={"probabilities", "headline",
                                                                  "advice", "sensitive_groups"})})
            metrics.BATCH_ROWS.labels("ok").inc()
        except (ValidationError, AirSenseError, ValueError, TypeError) as exc:
            msg = (exc.errors()[0]["msg"].replace("Value error, ", "") if isinstance(exc, ValidationError)
                   else getattr(exc, "message", str(exc)))
            errors.append(RowError(row=i, reason=msg))
            metrics.BATCH_ROWS.labels("failed").inc()
    log.info("Batch: %d ok, %d failed", len(results), len(errors))
    return BatchResponse(total=len(df), succeeded=len(results), failed=len(errors),
                         results=results, errors=errors)
