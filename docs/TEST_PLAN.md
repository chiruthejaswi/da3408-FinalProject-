# AirSense - Test Plan

## 1. Objectives
Show that AirSense (a) predicts correctly and robustly, (b) rejects bad input gracefully, (c) behaves identically through the UI and the API, and (d) meets the acceptance criteria in section 6.

## 2. Scope
| In scope | Out of scope |
|---|---|
| Data validation, feature engineering, run logging | Penetration/security testing, TLS/auth (not implemented) |
| REST API contract, validation, error handling, batch upload, metrics endpoint | Load testing beyond 100 sequential requests |
| Streamlit UI behaviour (with mocked and live backend) | Pixel-level visual regression, cross-browser matrix |
| Model quality on held-out *future* data | Real-world accuracy against live sensors |
| Docker/Compose files (static validation) | Running containers in CI (no Docker in the authoring sandbox - see README "Verify on your machine") |

## 3. Test levels and tools
| Level | What | Tool |
|---|---|---|
| Unit | AQI maths, validators, feature code, run-log | `pytest` |
| API / integration | Every endpoint against the **real trained model** | `pytest` + FastAPI `TestClient` |
| UI | Widget behaviour, error rendering, navigation; mocked backend + a live-backend smoke run | Streamlit `AppTest` |
| Acceptance | Model metrics, latency, robustness | `pytest` reading `metrics/*.json` |
| Static | Lint (PEP 8 subset), YAML/JSON validity of Compose/Prometheus/Grafana | `ruff`, `yaml`/`json` loaders |
| Pipeline | End-to-end reproducibility | `dvc repro`, `dvc status` |

## 4. Environment
Python 3.12, pinned versions in `requirements.txt` / `backend/requirements.txt` / `frontend/requirements.txt`; tests need the pipeline outputs (`dvc repro` first). Run: `python -m pytest` (or `python make_test_report.py` to also regenerate `TEST_REPORT.md`).

## 5. Entry / exit criteria
* **Entry:** `dvc repro` completed; `models/` and `metrics/` exist; lint clean.
* **Exit:** 100 % of test cases pass, all acceptance criteria met, no open critical defects.

## 6. Acceptance criteria
| ID | Criterion | How measured |
|---|---|---|
| AC-1 | Macro-F1 >= 0.80 on the held-out later-in-time test set | `metrics/train_metrics.json` |
| AC-2 | Recall >= 0.70 for **every** class, including rare ones | same file |
| AC-3 | p95 `/predict` latency < 300 ms (100 sequential requests, warm model) | `metrics/latency.json` written by test AC-03 |
| AC-4 | Serving feature list equals training feature list | test AC-04 |
| AC-5 | Malformed bodies never cause a 5xx | test AC-05 |
| AC-6 | Line coverage >= 70 % | `pytest-cov` |

Results and pass/fail counts: **`TEST_REPORT.md`** (auto-generated; includes the acceptance verdict).

## 7. Test data
* Real trained model + synthetic-but-realistic dataset (replaceable with the Kaggle file).
* Hand-built payloads for boundaries: negative, over-range, non-numeric, wrong date, empty body, unknown city, one reading only.
* CSV fixtures built inline: happy path, partial failure, missing `City`, no pollutant columns, header-only, binary garbage.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Tests depend on a trained model | `bash ci.sh` always runs `dvc repro` first |
| Synthetic data inflates quality metrics | Documented in HLD; UI banner; swap in real data and re-run the same suite |
| Latency measured in-process excludes network | Reported as such; threshold is generous (300 ms vs ~tens of ms) |

## 9. Test cases (53)
IDs are embedded in the test function names (`test_tcNN_...`, `test_acNN_...`) and the description is each test's docstring. Parametrised cases (e.g. TC-19) count as one case here and as several executions in the report.

| ID | Level | What is verified | File |
|---|---|---|---|
| TC-01 | Unit - data & pipeline | PM2.5 of 30 is the top of 'Good' (AQI 50); 60 is top of 'Satisfactory' (100). | `tests/test_pipeline.py` |
| TC-02 | Unit - data & pipeline | A missing reading gives NaN, not an exception. | `tests/test_pipeline.py` |
| TC-03 | Unit - data & pipeline | Every CPCB band maps to the right category. | `tests/test_pipeline.py` |
| TC-04 | Unit - data & pipeline | Synthetic data has the required schema and all six classes. | `tests/test_pipeline.py` |
| TC-05 | Unit - data & pipeline | validate() returns row/city counts and null percentages. | `tests/test_pipeline.py` |
| TC-06 | Unit - data & pipeline | A file without pollutant columns fails loudly. | `tests/test_pipeline.py` |
| TC-07 | Unit - data & pipeline | An empty dataset fails loudly. | `tests/test_pipeline.py` |
| TC-08 | Unit - data & pipeline | Ratios are computed and all model FEATURES exist. | `tests/test_pipeline.py` |
| TC-09 | Unit - data & pipeline | track_stage appends a success record. | `tests/test_pipeline.py` |
| TC-10 | Unit - data & pipeline | track_stage records failure details and re-raises the exception. | `tests/test_pipeline.py` |
| TC-11 | API / integration | /health reports the model as loaded. | `tests/test_backend.py` |
| TC-12 | API / integration | /cities lists supported cities. | `tests/test_backend.py` |
| TC-13 | API / integration | /predict returns category, confidence, probabilities and advice. | `tests/test_backend.py` |
| TC-14 | API / integration | Very low readings -> Good. | `tests/test_backend.py` |
| TC-15 | API / integration | Extreme readings -> Severe. | `tests/test_backend.py` |
| TC-16 | API / integration | Higher PM2.5 never yields a cleaner category. | `tests/test_backend.py` |
| TC-17 | API / integration | Only two readings given -> the other four are imputed and reported. | `tests/test_backend.py` |
| TC-18 | API / integration | One reading is not enough -> 422 with a friendly message. | `tests/test_backend.py` |
| TC-19 | API / integration | Negative or absurd values are rejected with 422. | `tests/test_backend.py` |
| TC-20 | API / integration | Text in a numeric field -> 422. | `tests/test_backend.py` |
| TC-21 | API / integration | Unsupported city -> 422 listing valid choices. | `tests/test_backend.py` |
| TC-22 | API / integration | No city -> 422. | `tests/test_backend.py` |
| TC-23 | API / integration | Invalid date string -> 422. | `tests/test_backend.py` |
| TC-24 | API / integration | Empty JSON body -> 422, never a 500. | `tests/test_backend.py` |
| TC-25 | API / integration | low_confidence is a boolean consistent with the confidence value. | `tests/test_backend.py` |
| TC-26 | API / integration | /model/info exposes provenance (run id, commit, metrics). | `tests/test_backend.py` |
| TC-27 | API / integration | /pipeline/status returns a DAG with the three stages and a summary. | `tests/test_backend.py` |
| TC-28 | API / integration | Template CSV has the expected header. | `tests/test_backend.py` |
| TC-29 | API / integration | Template file predicts every row. | `tests/test_backend.py` |
| TC-30 | API / integration | Bad rows are reported by row number; good rows still succeed. | `tests/test_backend.py` |
| TC-31 | API / integration | CSV without City -> 400 with clear message. | `tests/test_backend.py` |
| TC-32 | API / integration | CSV with City only -> 400. | `tests/test_backend.py` |
| TC-33 | API / integration | Header-only and binary files are rejected, not crashed on. | `tests/test_backend.py` |
| TC-34 | API / integration | Prometheus endpoint exposes request, prediction and drift metrics. | `tests/test_backend.py` |
| TC-35 | UI (Streamlit AppTest) | Predict page shows title, city dropdown and 6 reading inputs. | `tests/test_ui.py` |
| TC-36 | UI (Streamlit AppTest) | Clicking an example fills city and readings. | `tests/test_ui.py` |
| TC-37 | UI (Streamlit AppTest) | Predict with 0 readings -> friendly warning, no API call. | `tests/test_ui.py` |
| TC-38 | UI (Streamlit AppTest) | Two readings -> result card with category and confidence. | `tests/test_ui.py` |
| TC-39 | UI (Streamlit AppTest) | Backend unreachable -> readable error, no stack trace. | `tests/test_ui.py` |
| TC-40 | UI (Streamlit AppTest) | 422 from the API is shown with field-level details. | `tests/test_ui.py` |
| TC-41 | UI (Streamlit AppTest) | Connection errors become ApiUnavailable. | `tests/test_ui.py` |
| TC-42 | UI (Streamlit AppTest) | API_URL env var controls the backend address (loose coupling). | `tests/test_ui.py` |
| TC-43 | UI (Streamlit AppTest) | An example whose city the model lacks keeps the current city but fills readings. | `tests/test_ui.py` |
| TC-44 | API / integration | If the model cannot be loaded, /predict gives 503 (not 500) and /health says degraded. | `tests/test_backend.py` |
| TC-45 | API / integration | Batch processing increments the ok/failed row counters in /metrics. | `tests/test_backend.py` |
| TC-46 | Unit - data & pipeline | preprocess.make_transform fills blanks with city medians, nulls negatives and clips outliers. | `tests/test_pipeline.py` |
| TC-47 | Unit - data & pipeline | train.evaluate reports accuracy, macro-F1 and one recall per class. | `tests/test_pipeline.py` |
| TC-48 | Unit - data & pipeline | Three candidate models are defined; git_commit() always returns a string. | `tests/test_pipeline.py` |
| AC-01 | Acceptance | AC-1: held-out (future) macro-F1 >= 0.80. | `tests/test_acceptance.py` |
| AC-02 | Acceptance | AC-2: no class (incl. rare Severe) has recall below 0.70. | `tests/test_acceptance.py` |
| AC-03 | Acceptance | AC-3: p95 /predict latency < 300 ms over 100 requests. | `tests/test_acceptance.py` |
| AC-04 | Acceptance | AC-4: serving feature list equals the training feature list. | `tests/test_acceptance.py` |
| AC-05 | Acceptance | AC-5: fuzzed bodies never produce a 5xx. | `tests/test_acceptance.py` |

## 10. Traceability
| Requirement | Cases |
|---|---|
| Correct prediction & ordering | TC-13..16, TC-25 |
| Missing readings handled | TC-17, TC-18 |
| Input validation / foolproof | TC-19..24, TC-37, TC-40, AC-05 |
| Batch upload | TC-29..33, TC-45 |
| Observability | TC-34, TC-45 |
| Pipeline status / console | TC-49..53 |
| Resilience (model missing, service down) | TC-39, TC-41, TC-44 |
| Loose coupling / configurability | TC-42, AC-04 |
| Pipeline code | TC-01..10, TC-46..48, TC-54 |
| Model quality | AC-1..2 |
| Performance | AC-3 |
