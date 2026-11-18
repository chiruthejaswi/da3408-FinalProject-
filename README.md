# AirSense: Air Quality Index Prediction for Indian Cities
Name : Chiruthejaswi 
Roll No : DA24B036
Video link : https://drive.google.com/file/d/1HX6XCuuyq7L1jvhXwMATJ3y1VMX1hfql/view?usp=sharing

Streamlit UI + FastAPI backend that predicts the CPCB AQI category (**Good / Satisfactory / Moderate / Poor / Very Poor / Severe**) from pollutant readings (PM2.5, PM10, NO2, SO2, CO, O3), with a confidence score and health advice. Data engineering runs on Ray, the pipeline on DVC, experiments on MLflow, and the whole thing is monitored with Prometheus + Grafana.

```
Streamlit :8501 --REST (API_URL)--> FastAPI :8000 --> model (MLflow format)
   |  metrics :8001                    |  /metrics            ^
   v                                   v                      | models/ (read-only)
Prometheus :9090 -------------------> Grafana :3000       dvc repro: ingest -> preprocess (Ray) -> train (MLflow :5000)
```
## Prerequisites

Python 3.12 (also worked on 3.14), about 1 GB free disk for the Python-only steps. Step 7 additionally needs Docker Desktop / Docker Engine with Compose and about **6 GB** free disk (images and build cache).

## Step 1: Python environment

```
python -m venv .venv
source .venv/bin/activate          
pip install -r requirements.txt -r backend/requirements.txt -r frontend/requirements.txt
pip install pytest pytest-cov httpx ruff jupyter
dvc commit -f                      
dvc status                         
```

## Step 2: Look at the data and results (notebooks)

| Notebook | What it shows | Needs |
|---|---|---|
| `01_EDA.ipynb` | Class balance, missing values, city differences, seasonality, why the split is by time | data (`dvc repro`) |
| `02_Pipeline_and_Training.ipynb` | DVC DAG, run history, Ray throughput, MLflow runs, confusion matrix, feature importance, confidence calibration, **model vs. the plain CPCB formula** | pipeline outputs |
| `03_API_Demo.ipynb` | Every endpoint, bad-input handling, CSV batch, model info, metrics, latency | API running |
| `04_Drift_Demo.ipynb` | Simulated data shift and the drift gauge that Prometheus alerts on | API running (restart it first for a clean baseline) |


## Step 3: Run the tests

```
python -m pytest                   # counts: see docs/TEST_REPORT.md
python make_test_report.py         # tests + coverage + acceptance check -> docs/TEST_REPORT.md
```

## Step 4: Run the pipeline (data engineering + training)

```
cp ~/Downloads/archive/city_day.csv data/raw/city_day.csv   
rm -rf mlflow.db mlruns                                    
dvc repro                                                  # ingest -> preprocess (Ray) -> train (MLflow)
grep source metrics/data_quality.json                       
dvc dag                                                    # print the pipeline DAG
```

Outputs: `data/interim/` (validated data), `data/processed/`, `models/airsense_model/`, `models/model_meta.json`, `metrics/*.json`. Check `metrics/data_quality.json` for `"source": "real"`. MLflow runs are stored in `mlflow.db` (view with `mlflow ui --backend-store-uri sqlite:///mlflow.db`). Each run is tagged with the Git commit and dataset hash; reproduce a model with `git checkout <commit> && dvc repro`.

## Step 5: Start the backend

```
uvicorn backend.main:app --port 8000
```

OpenAPI docs: <http://localhost:8000/docs> · Metrics: <http://localhost:8000/metrics>

## Step 6: Start the frontend

```
cd frontend
API_URL=http://localhost:8000 python run.py     # Windows (cmd): set API_URL=http://localhost:8000  then  python run.py
```

UI: <http://localhost:8501> (Predict, Batch (CSV), Pipeline, Help). `run.py` starts the UI's metrics port (:8001) and then Streamlit. Frontend and backend are independent: the UI only knows `API_URL`.

## Step 7: Full stack with Docker (app + monitoring)

```
docker compose up --build
```

| Service | URL |
|---|---|
| App (UI) | <http://localhost:8501> |
| API docs | <http://localhost:8000/docs> |
| MLflow | <http://localhost:5000> |
| Prometheus | <http://localhost:9090> (targets, alerts) |
| Grafana | <http://localhost:3000> (admin / admin) → **AirSense - Live Monitoring** (refresh 5 s) |

The containerised MLflow starts empty. To fill it by running the pipeline in a container: `docker compose --profile train run --rm pipeline dvc repro -f`, then `docker compose restart backend`.

## Step 8: Alerts and drift

Stop the backend for ~20 s: `BackendDown` fires at <http://localhost:9090/alerts>. Send shifted data (see `04_Drift_Demo.ipynb`): `InputDrift` fires when a pollutant's recent mean moves by more than 0.5 training standard deviation (a medium effect size; see `04_Drift_Demo.ipynb`) for 2 minutes.

## Files

| File / folder | Purpose |
|---|---|
| `ingest.py`, `preprocess.py`, `train.py` | The three DVC stages (Ray in `preprocess.py`, MLflow in `train.py`) |
| `common.py` | Shared constants, feature recipe and run-history logger (used by pipeline **and** backend) |
| `params.yaml`, `dvc.yaml`, `dvc.lock`, `MLproject`, `conda.yaml`, `requirements.txt` | Parameters, pipeline DAG, reproducible environment |
| `backend/` | FastAPI: `main.py` (routes), `predictor.py` (model, advice, errors), `schemas.py`, `metrics.py`, `pipeline_status.py`, `config.py`, `Dockerfile` |
| `frontend/` | Streamlit: `app.py`, `api_client.py`, `ui_metrics.py`, `run.py`, `user_manual.md`, `Dockerfile` |
| `docker-compose.yml`, `Dockerfile.pipeline`, `mlflow_server/` | Containers |
| `prometheus.yml`, `alert_rules.yml`, `gen_dashboard.py`, `grafana/` | Monitoring (5 s scrape, 5 alert rules, 16-panel provisioned dashboard) |
| `tests/` | Unit, API, UI (Streamlit AppTest) and acceptance tests (counts: `docs/TEST_REPORT.md`) |
| `diagnose.py`, `diagnose_ceiling.py`, `diagnose_labels.py` | Read-only diagnostics: model vs formula, effect of extra pollutants, how the labels relate to the formula |
| `make_test_report.py`, `make_diagram.py`, `ci.sh` | Test report generator, architecture diagram generator, local CI (`lint -> dvc repro -> tests`) |
| `docs/` | Architecture diagram + explanation, HLD, LLD (endpoint specs), test plan, test report, user manual, DVC DAG |
| `data/`, `models/`, `metrics/` | DVC-managed pipeline outputs |

## Where to find each rubric item

| Rubric item | Where |
|---|---|
| UI/UX, responsive, foolproof, manual | `frontend/app.py`, in-app **Help**, `docs/USER_MANUAL.md` |
| Pipeline visualisation, console, throughput | UI **Pipeline** page; `02_Pipeline_and_Training.ipynb` |
| Architecture, HLD, LLD | `docs/ARCHITECTURE.md`, `docs/HLD.md`, `docs/LLD.md` |
| Loose coupling via configurable REST | `frontend/api_client.py` (`API_URL`), separate Dockerfiles/services |
| Logging, exceptions, OO, docstrings | `backend/`, `common.py` |
| Tests, test plan, report, acceptance | `tests/`, `docs/TEST_PLAN.md`, `docs/TEST_REPORT.md` |
| Data engineering with Ray | `preprocess.py`, `metrics/pipeline_metrics.json` |
| DVC CI + DAG, Git/DVC versioning | `dvc.yaml`, `dvc.lock`, `docs/dvc_dag.txt`, `ci.sh` |
| Experiment tracking beyond autolog | `train.py` (tags, val/test metrics, per-class recall, plots, importance, stats, data hash) |
| Prometheus + Grafana, all components | `backend/metrics.py`, `frontend/ui_metrics.py`, `prometheus.yml`, `alert_rules.yml`, `grafana/` |
| MLflow model, MLproject, FastAPI, Docker, Compose | `train.py`, `MLproject`, `backend/`, `docker-compose.yml` |

## Notes and limitations
* **Synthetic vs real data.** On the synthetic demo data the model only *matches* the plain CPCB formula (its labels are that formula). On the real Kaggle data (author's run) the model **beats** it: macro-F1 0.770 vs 0.676, with 99.4 % of predictions exact or one category off. See `docs/HLD.md` §2.1.
* **Acceptance criteria were revised after real data.** The original targets (macro-F1 >= 0.80, every class recall >= 0.70) were not met on real data (0.770; Good 0.686). The reasons and the revised criteria are recorded in `docs/TEST_PLAN.md` §6.1, and both sets are reported in `docs/TEST_REPORT.md`. `diagnose.py`, `diagnose_ceiling.py` and `diagnose_labels.py` reproduce the evidence.
* Monitoring covers input drift and confidence, **not** production accuracy (no ground-truth feedback).
* Ray throughput varies with machine load (about 4,000-7,400 rows/s transform on this data); at this size Ray start-up dominates the end-to-end figure.
* Latency was measured in-process (test client), not over a network.
