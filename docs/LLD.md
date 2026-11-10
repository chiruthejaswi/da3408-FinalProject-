# AirSense - Low-Level Design (LLD)

Base URL (default): `http://localhost:8000` · Interactive OpenAPI: `/docs` · Content type: `application/json` (batch: `multipart/form-data`).

## 1. Endpoint summary
| Method | Path | Purpose | Success |
|---|---|---|---|
| POST | `/predict` | Predict AQI category for one city/reading set | 200 |
| POST | `/predict/batch` | Predict many rows from an uploaded CSV | 200 |
| GET | `/template.csv` | Example CSV for batch upload | 200 (text/plain) |
| GET | `/cities` | Supported cities | 200 |
| GET | `/model/info` | Model version, provenance, metrics | 200 |
| GET | `/pipeline/status` | DVC DAG, run history, pipeline metrics, MLflow runs | 200 |
| GET | `/health` | Liveness + model-loaded flag | 200 |
| GET | `/metrics` | Prometheus exposition format | 200 |

## 2. `POST /predict`
**Request body** (`PredictRequest`)

| Field | Type | Required | Constraint | Unit / note |
|---|---|---|---|---|
| `city` | string | yes | min length 1; must be a trained city, else 422 `unknown_city` | |
| `date` | string `YYYY-MM-DD` | no | valid date; default = today | month used for seasonality |
| `pm25` | number | no* | 0 ≤ x ≤ 1000 | µg/m³ |
| `pm10` | number | no* | 0 ≤ x ≤ 2000 | µg/m³ |
| `no2` | number | no* | 0 ≤ x ≤ 1000 | µg/m³ |
| `so2` | number | no* | 0 ≤ x ≤ 2000 | µg/m³ |
| `co` | number | no* | 0 ≤ x ≤ 100 | **mg/m³** |
| `o3` | number | no* | 0 ≤ x ≤ 1000 | µg/m³ |

\* **At least 2** of the six readings are required. Missing readings are imputed with the city's training-period median and listed in `imputed_fields`. Unknown extra fields are ignored.

Example:
```json
{"city": "Delhi", "date": "2026-11-02", "pm25": 180, "pm10": 320, "co": 2.5}
```

**Response 200** (`Prediction`)
```json
{
  "city": "Delhi",
  "category": "Very Poor",
  "confidence": 0.9996,
  "probabilities": {
    "Good": 0.0,
    "Satisfactory": 0.0,
    "Moderate": 0.0,
    "Poor": 0.0,
    "Very Poor": 0.9996,
    "Severe": 0.0004
  },
  "color": "#FF0000",
  "headline": "Air quality is very poor",
  "advice": "Respiratory illness on prolonged exposure. Avoid outdoor exercise.",
  "sensitive_groups": "Stay indoors, keep windows closed, use an air purifier if available.",
  "imputed_fields": [
    "NO2",
    "SO2",
    "O3"
  ],
  "low_confidence": false
}
```
`category` ∈ {Good, Satisfactory, Moderate, Poor, Very Poor, Severe}; `confidence` ∈ [0,1] (= max probability); `probabilities` sum to 1; `low_confidence` = `confidence < 0.60`.

## 3. `POST /predict/batch`
**Request:** multipart field `file` = CSV. Header must contain `City` and at least one of `PM2.5, PM10, NO2, SO2, CO, O3`; `Date` optional. Limits: 5 MB, 5 000 rows (env-configurable). Each row is validated with the **same rules as `/predict`**.

**Response 200** (`BatchResponse`) - *bad rows never fail the whole file*:
```json
{
  "total": 4, "succeeded": 2, "failed": 2,
  "results": [{"row": 2, "city": "Delhi", "category": "Very Poor", "confidence": 0.97,
               "color": "#FF0000", "imputed_fields": ["SO2"], "low_confidence": false}],
  "errors":  [{"row": 4, "reason": "City 'Atlantis' is not supported. Choose one of: ..."},
              {"row": 5, "reason": "Input should be greater than or equal to 0"}]
}
```
`row` is the CSV line number (header = line 1).

## 4. Other endpoints
| Endpoint | Response shape |
|---|---|
| `GET /health` | `{"status": "ok"\|"degraded", "model_loaded": bool}` |
| `GET /cities` | `{"cities": ["Ahmedabad", "Aizawl", ...]}` (sorted) |
| `GET /model/info` | `{model_name, mlflow_run_id, git_commit, dataset_md5, trained_at, data_source, classes[], features[], cities[], test_metrics{accuracy, macro_f1, weighted_f1, recall_<class>...}, candidate_val_macro_f1{}}` |
| `GET /pipeline/status` | `{dag{nodes[], edges[[from,to]]}, history[{stage,status,started_at,seconds,error?,traceback?}] (newest first), latest_by_stage{}, summary{success,failed,total}, pipeline_metrics{}, data_quality{}, train_metrics{}, mlflow_runs[{run_id,name,status,role,git_commit,model,val_macro_f1,test_macro_f1}], links{mlflow,grafana}}` - `mlflow_runs` is `[]` if MLflow is unreachable |
| `GET /template.csv` | CSV text with header + 2 sample rows |
| `GET /metrics` | Prometheus text format |

## 5. Error contract (uniform JSON)
```json
{"error": "<machine_code>", "message": "<human text>", "details": [{"field": "pm25", "message": "..."}]}
```
| HTTP | `error` | When |
|---|---|---|
| 422 | `validation_error` | Type/range/required/date failures, fewer than 2 readings (`details` lists each field) |
| 422 | `unknown_city` | City not among trained cities (message lists valid cities) |
| 422 | `invalid_input` | Business-rule failure after validation |
| 400 | `invalid_file` | Unreadable CSV, missing `City`/pollutant columns, empty file, too large, too many rows |
| 503 | `model_unavailable` | Model/metadata failed to load (service stays up; `/health` reports `degraded`) |
| 500 | `internal_error` | Anything unexpected - generic message, full traceback only in server logs |

## 6. Class design (OO)
| Class / module | Responsibility | Key methods |
|---|---|---|
| `Predictor` (`backend/predictor.py`) | Owns model + metadata; turns row dicts into `Prediction`s | `predict_one`, `predict_many`, `info`, `_row_to_frame` (validate city, impute, clip, engineer) |
| `HealthAdvisor` (`backend/predictor.py`) | Category → colour/headline/advice from JSON | `for_category` |
| `PredictRequest`, `Prediction`, `BatchResponse`, `RowError` (`backend/schemas.py`) | Interface contract (Pydantic) | `enough_readings` validator |
| `AirSenseError` + 4 subclasses (`backend/predictor.py`) | Typed, user-facing failures carrying HTTP status + code | - |
| `backend/pipeline_status.py` | Pure functions: build DAG from `dvc.yaml`, read history/metrics, query MLflow | `build_status`, `dag_from_dvc_yaml`, `mlflow_runs` |
| `backend/metrics.py` | Prometheus metric objects + drift window | `observe_inputs` |
| `ApiClient` (`frontend/api_client.py`) | UI's only gateway to the backend | `predict`, `predict_batch`, `pipeline_status`, ... |
| `track_stage` (`common.py`) | Context manager recording stage outcome | - |

Shared code between training and serving is limited to `common.py` (single definition of the feature recipe, avoiding training/serving skew). The **frontend** shares nothing with the backend.

## 7. Inference algorithm (per row)
1. Validate schema (Pydantic) and `city ∈ cities`.
2. For each of the 6 pollutants: use the user value, else `medians[pollutant][city]` (fallback: global median) and record it as imputed; soft-cap at 5 × the training 99.9th percentile.
3. `month` from `date` (default today); `pm_ratio = PM2.5/(PM10+1e-6)`; `nox_so2 = NO2/(SO2+1e-6)`.
4. Feature order = `FEATURES` = `[PM2.5, PM10, NO2, SO2, CO, O3, month, pm_ratio, nox_so2]`.
5. `predict_proba` → map `model.classes_` → six classes → argmax = category; confidence = max.
6. Look up advice; update Prometheus metrics; log.

## 8. Pipeline interfaces (files)
| Artifact | Format | Producer → consumer |
|---|---|---|
| `data/raw/city_day.csv` (optional) | Real Kaggle CSV: `City, Date, PM2.5, PM10, NO2, SO2, CO, O3, ..., AQI_Bucket`. **Input only**, never modified | user → ingest |
| `data/interim/city_day.csv` | Validated data (the real file if present, else synthetic) | ingest → preprocess |
| `data/processed/{train,test}.csv` | raw columns + `month, pm_ratio, nox_so2, label` | preprocess → train |
| `data/processed/stats.json` | `{medians{pollutant{city,__global__}}, caps{pollutant}}` | preprocess → train → backend (via meta) |
| `models/airsense_model/` | MLflow sklearn flavour (cloudpickle) | train → backend |
| `models/model_meta.json` | classes, features, cities, medians, caps, feature mean/std, run id, git commit, metrics | train → backend |
| `metrics/run_history.jsonl` | one JSON per stage run: `stage, status, started_at, seconds, error?, traceback?` | all stages → backend → UI |
| `metrics/{data_quality,pipeline_metrics,train_metrics}.json` | DVC metrics | stages → backend → UI |

## 9. Prometheus metrics
**Backend** (`:8000/metrics`)

| Metric | Type | Labels |
|---|---|---|
| `airsense_http_requests_total` | counter | method, path, status |
| `airsense_http_request_seconds` | histogram | path |
| `airsense_errors_total` | counter | type (`validation`, `unknown_city`, `invalid_file`, `unexpected`, ...) |
| `airsense_predictions_total` | counter | category |
| `airsense_prediction_confidence` | histogram | - |
| `airsense_input_value` | histogram | feature |
| `airsense_input_drift_zscore` | gauge | feature |
| `airsense_batch_rows_total` | counter | outcome (`ok`, `failed`) |
| `airsense_model_loaded`, `airsense_model_info` | gauge | model, run_id, git_commit |

**Frontend** (`:8001`): `airsense_ui_page_views_total{page}`, `airsense_ui_predict_total{outcome}`, `airsense_ui_batch_total{outcome}`, `airsense_ui_api_calls_total{endpoint,outcome}`, `airsense_ui_api_seconds{endpoint}`.

## 10. Configuration (environment variables)
| Variable | Component | Default |
|---|---|---|
| `API_URL` | frontend | `http://localhost:8000` |
| `UI_METRICS_PORT` | frontend | `8001` |
| `MODEL_DIR`, `META_PATH` | backend | `models/airsense_model`, `models/model_meta.json` |
| `METRICS_DIR`, `DVC_YAML` | backend | `metrics`, `dvc.yaml` |
| `MLFLOW_TRACKING_URI`, `MLFLOW_UI_URL`, `GRAFANA_URL` | backend / training | `sqlite:///mlflow.db`, `http://localhost:5000`, `http://localhost:3000` |
| `MAX_BATCH_ROWS`, `MAX_UPLOAD_BYTES` | backend | `5000`, `5242880` |
| `params.yaml` | pipeline | split date, clip quantile, Ray CPUs, model hyper-parameters |

## 11. Coding standards
PEP 8 (checked with `ruff` rules E,F, line length 130), docstrings on all public functions/classes, type hints on most public signatures, `logging` everywhere (no `print` in services), explicit exception types, no bare `except` (the few broad handlers are annotated with `noqa` and either re-raise, convert to a typed error, or fall back safely).
