"""Pipeline end-to-end smoke test, pipeline-status helpers and Pipeline UI page (TC-49 .. TC-54)."""
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_tc49_dag_built_from_dvc_yaml():
    """The DAG is derived from dvc.yaml: ingest -> preprocess -> train."""
    from backend.pipeline_status import dag_from_dvc_yaml
    dag = dag_from_dvc_yaml(str(ROOT / "dvc.yaml"))
    assert dag["nodes"] == ["ingest", "preprocess", "train"]
    assert ["ingest", "preprocess"] in dag["edges"] and ["preprocess", "train"] in dag["edges"]


def test_tc50_missing_pipeline_files_degrade_gracefully(tmp_path):
    """Missing history/dvc.yaml give empty results instead of errors."""
    from backend.pipeline_status import dag_from_dvc_yaml, read_history
    assert read_history(str(tmp_path)) == []
    assert dag_from_dvc_yaml(str(tmp_path / "nope.yaml")) == {"nodes": [], "edges": []}


def test_tc51_unreachable_mlflow_returns_empty_list():
    """If MLflow cannot be reached the run table is simply empty."""
    from backend.pipeline_status import mlflow_runs
    assert mlflow_runs("http://127.0.0.1:9", "airsense") == []


def test_tc52_corrupt_history_lines_are_skipped(tmp_path):
    """A half-written line in run_history.jsonl does not break the console."""
    from backend.pipeline_status import read_history
    (tmp_path / "run_history.jsonl").write_text('{"stage": "a", "status": "success"}\n{broken\n')
    assert [r["stage"] for r in read_history(str(tmp_path))] == ["a"]


def test_tc53_pipeline_page_renders_with_real_status(client, monkeypatch):
    """The Pipeline page renders all five tabs from the real /pipeline/status and /model/info payloads."""
    sys.path.insert(0, str(ROOT / "frontend"))
    from api_client import ApiClient
    monkeypatch.setattr(ApiClient, "health", lambda self: {"model_loaded": True})
    monkeypatch.setattr(ApiClient, "pipeline_status", lambda self: client.get("/pipeline/status").json())
    monkeypatch.setattr(ApiClient, "model_info", lambda self: client.get("/model/info").json())
    at = AppTest.from_file(str(ROOT / "frontend" / "app.py"), default_timeout=30).run()
    at.radio[0].set_value("⚙️ Pipeline").run()
    assert not at.exception
    assert len(at.tabs) == 5 and [m.label for m in at.metric][:3] == ["Pipeline runs logged", "Successful", "Failed"]


@pytest.mark.slow
def test_tc54_pipeline_end_to_end_on_tiny_data(tmp_path, monkeypatch):
    """ingest -> Ray preprocess -> train all run on a tiny dataset and export a loadable model."""
    import mlflow
    import mlflow.sklearn
    import ingest
    import preprocess
    import train
    params = yaml.safe_load((ROOT / "params.yaml").read_text())
    params["data"]["synthetic_rows_per_city"] = 120
    params["preprocess"].update(test_cutoff_date="2015-03-15", ray_num_cpus=1)
    params["train"].update(random_forest={"n_estimators": 10, "max_depth": 6, "min_samples_leaf": 2},
                           hist_gb={"max_iter": 20, "learning_rate": 0.2, "max_depth": 4},
                           logreg={"C": 1.0, "max_iter": 300})
    (tmp_path / "params.yaml").write_text(yaml.safe_dump(params))
    shutil.copy(ROOT / "backend" / "health_advice.json", tmp_path / "health_advice.json")
    previous_uri = mlflow.get_tracking_uri()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path}/m.db")
    try:
        ingest.main()
        preprocess.main()
        train.main()
    finally:
        mlflow.set_tracking_uri(previous_uri)
    meta = json.loads((tmp_path / "models" / "model_meta.json").read_text())
    assert meta["model_name"] in {"logreg", "random_forest", "hist_gb"} and len(meta["cities"]) == 10
    assert (tmp_path / "metrics" / "pipeline_metrics.json").exists()
    model = mlflow.sklearn.load_model(str(tmp_path / "models" / "airsense_model"))
    assert hasattr(model, "predict_proba")
