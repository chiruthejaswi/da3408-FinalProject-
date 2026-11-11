# Evidence screenshots

Taken from the running Docker Compose stack (`docker compose up`).

| File | Shows |
|---|---|
| `predict_page.png` | Predict page: city, date, six pollutant inputs with units, example buttons |
| `predict_result.png` | Result after pressing *Predict air quality*: colour-coded category, confidence, health advice |
| `pipeline_dag.png` | Pipeline console: DAG with status colours, run counts, last run per stage |
| `pipeline_run_console.png` | Run console: every stage run with status and duration (successes and failures) |
| `pipeline_data_engineering.png` | Ray data-engineering throughput (rows/s) and per-stage seconds |
| `pipeline_model.png` | Selected model, MLflow run ID, Git commit and held-out test metrics |
| `grafana_dashboard_top.png` | Live dashboard: model loaded, request rate, error rate, p95 latency, predictions served |
| `grafana_dashboard_drift.png` | Predictions by category, confidence, and the input-drift z-scores after a shifted load |
| `grafana_dashboard_ui_metrics.png` | Frontend instrumentation (page views, UI-to-API calls) and scrape-target health |
| `prometheus_targets.png` | Prometheus scraping the backend (:8000), frontend (:8001) and itself, all UP |
| `prometheus_alerts.png` | The five alert rules; `InputDrift` firing |
| `prometheus_alert_inputdrift_firing.png` | The `InputDrift` rule (threshold 0.5) firing for PM2.5 and PM10 |
| `mlflow_runs.png` | MLflow run table: three candidate runs and the final run |
| `mlflow_final_run.png` | Final run: metrics, `git_commit` / `dataset_md5` / `data_source` tags |
