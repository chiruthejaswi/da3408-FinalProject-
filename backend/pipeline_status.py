"""Collect pipeline information (DVC DAG, run history, metrics, MLflow runs)."""
import json
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger("pipeline_status")


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def dag_from_dvc_yaml(path: str) -> dict:
    """Build {nodes, edges} by matching each stage's deps to other stages' outs."""
    try:
        stages = yaml.safe_load(Path(path).read_text(encoding="utf-8")).get("stages", {})
    except (OSError, yaml.YAMLError):
        return {"nodes": [], "edges": []}

    def names(items):
        return [next(iter(i)) if isinstance(i, dict) else i for i in items or []]

    producers = {o: s for s, d in stages.items() for o in names(d.get("outs"))}
    edges = sorted({(producers[dep], s) for s, d in stages.items()
                    for dep in names(d.get("deps")) if dep in producers and producers[dep] != s})
    return {"nodes": list(stages), "edges": [list(e) for e in edges]}


def read_history(metrics_dir: str, limit: int = 50) -> list:
    """Latest `limit` stage run records (newest first)."""
    path = Path(metrics_dir) / "run_history.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out[::-1]


def mlflow_runs(tracking_uri: str, experiment: str, limit: int = 20) -> list:
    """Recent MLflow runs; returns [] if the tracking server is unreachable."""
    # Fail fast: MLflow's default is several retries with exponential backoff (minutes), which
    # would freeze the Pipeline page whenever the tracking server is down.
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")
    try:
        import mlflow
        client = mlflow.MlflowClient(tracking_uri=tracking_uri)
        exp = client.get_experiment_by_name(experiment)
        if exp is None:
            return []
        runs = client.search_runs([exp.experiment_id], max_results=limit,
                                  order_by=["attributes.start_time DESC"])
        return [{"run_id": r.info.run_id, "name": r.info.run_name, "status": r.info.status,
                 "role": r.data.tags.get("role"), "git_commit": r.data.tags.get("git_commit", "")[:10],
                 "model": r.data.params.get("model"),
                 "val_macro_f1": r.data.metrics.get("val_macro_f1"),
                 "test_macro_f1": r.data.metrics.get("test_macro_f1")} for r in runs]
    except Exception as exc:  # noqa: BLE001
        log.warning("MLflow unavailable: %s", exc)
        return []


def build_status(settings) -> dict:
    """Assemble the full /pipeline/status payload."""
    mdir = Path(settings.METRICS_DIR)
    history = read_history(settings.METRICS_DIR)
    latest = {}
    for rec in history:  # newest first -> first seen per stage is latest
        latest.setdefault(rec["stage"], rec)
    return {
        "dag": dag_from_dvc_yaml(settings.DVC_YAML),
        "history": history,
        "latest_by_stage": latest,
        "summary": {"success": sum(r["status"] == "success" for r in history),
                    "failed": sum(r["status"] == "failed" for r in history),
                    "total": len(history)},
        "pipeline_metrics": _read_json(mdir / "pipeline_metrics.json"),
        "data_quality": _read_json(mdir / "data_quality.json"),
        "train_metrics": _read_json(mdir / "train_metrics.json"),
        "mlflow_runs": mlflow_runs(settings.MLFLOW_TRACKING_URI, settings.MLFLOW_EXPERIMENT),
        "links": {"mlflow": settings.MLFLOW_UI_URL, "grafana": settings.GRAFANA_URL},
    }
