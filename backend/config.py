"""Backend configuration, all overridable via environment variables."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
MODEL_DIR = os.getenv("MODEL_DIR", "models/airsense_model")
META_PATH = os.getenv("META_PATH", "models/model_meta.json")
METRICS_DIR = os.getenv("METRICS_DIR", "metrics")
DVC_YAML = os.getenv("DVC_YAML", "dvc.yaml")
ADVICE_PATH = os.getenv("ADVICE_PATH", str(BASE / "health_advice.json"))
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db")
MLFLOW_EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "airsense")
MLFLOW_UI_URL = os.getenv("MLFLOW_UI_URL", "http://localhost:5000")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000")
LOG_DIR = os.getenv("LOG_DIR", "logs")
MAX_BATCH_ROWS = int(os.getenv("MAX_BATCH_ROWS", "5000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
