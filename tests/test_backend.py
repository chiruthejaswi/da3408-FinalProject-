"""API tests (TC-11 .. TC-34) against the real model."""
import io

import pytest


def test_tc11_health(client):
    """/health reports the model as loaded."""
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["model_loaded"] is True


def test_tc12_cities(client):
    """/cities lists supported cities."""
    cities = client.get("/cities").json()["cities"]
    assert "Delhi" in cities and len(cities) >= 2


def test_tc13_predict_response_shape(client, valid_payload):
    """/predict returns category, confidence, probabilities and advice."""
    body = client.post("/predict", json=valid_payload).json()
    for key in ["category", "confidence", "probabilities", "color", "advice", "imputed_fields"]:
        assert key in body
    assert abs(sum(body["probabilities"].values()) - 1) < 0.01


def test_tc14_clean_air_is_good(client):
    """Very low readings -> Good."""
    r = client.post("/predict", json={"city": "Aizawl", "pm25": 8, "pm10": 20, "no2": 8,
                                      "so2": 4, "co": 0.2, "o3": 20, "date": "2026-07-01"})
    assert r.json()["category"] == "Good"


def test_tc15_heavy_pollution_is_severe(client):
    """Extreme readings -> Severe."""
    r = client.post("/predict", json={"city": "Delhi", "pm25": 400, "pm10": 600,
                                      "no2": 300, "so2": 60, "co": 20, "o3": 60})
    assert r.json()["category"] == "Severe"


def test_tc16_ordering_is_monotonic(client):
    """Higher PM2.5 never yields a cleaner category."""
    order = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
    idx = [order.index(client.post("/predict", json={"city": "Delhi", "pm25": v, "pm10": v * 2}
                                   ).json()["category"]) for v in (10, 50, 100, 200, 300)]
    assert idx == sorted(idx)


def test_tc17_missing_readings_are_imputed(client):
    """Only two readings given -> the other four are imputed and reported."""
    body = client.post("/predict", json={"city": "Delhi", "pm25": 120, "pm10": 250}).json()
    assert sorted(body["imputed_fields"]) == ["CO", "NO2", "O3", "SO2"]


def test_tc18_too_few_readings_rejected(client):
    """One reading is not enough -> 422 with a friendly message."""
    r = client.post("/predict", json={"city": "Delhi", "pm25": 120})
    assert r.status_code == 422 and "at least 2" in str(r.json()).lower()


@pytest.mark.parametrize("field,value", [("pm25", -1), ("pm25", 5000), ("co", 500), ("no2", -0.1)])
def test_tc19_out_of_range_rejected(client, valid_payload, field, value):
    """Negative or absurd values are rejected with 422."""
    valid_payload[field] = value
    r = client.post("/predict", json=valid_payload)
    assert r.status_code == 422 and r.json()["error"] == "validation_error"


def test_tc20_non_numeric_rejected(client, valid_payload):
    """Text in a numeric field -> 422."""
    valid_payload["pm25"] = "abc"
    assert client.post("/predict", json=valid_payload).status_code == 422


def test_tc21_unknown_city_rejected(client, valid_payload):
    """Unsupported city -> 422 listing valid choices."""
    valid_payload["city"] = "Atlantis"
    r = client.post("/predict", json=valid_payload)
    assert r.status_code == 422 and r.json()["error"] == "unknown_city"


def test_tc22_missing_city_rejected(client):
    """No city -> 422."""
    assert client.post("/predict", json={"pm25": 50, "pm10": 80}).status_code == 422


def test_tc23_bad_date_rejected(client, valid_payload):
    """Invalid date string -> 422."""
    valid_payload["date"] = "31-31-2026"
    assert client.post("/predict", json=valid_payload).status_code == 422


def test_tc24_empty_body_rejected(client):
    """Empty JSON body -> 422, never a 500."""
    assert client.post("/predict", json={}).status_code == 422


def test_tc25_low_confidence_flag_type(client, valid_payload):
    """low_confidence is a boolean consistent with the confidence value."""
    b = client.post("/predict", json=valid_payload).json()
    assert isinstance(b["low_confidence"], bool) and b["low_confidence"] == (b["confidence"] < 0.6)


def test_tc26_model_info(client):
    """/model/info exposes provenance (run id, commit, metrics)."""
    info = client.get("/model/info").json()
    assert info["mlflow_run_id"] and "git_commit" in info and info["test_metrics"]["macro_f1"] > 0


def test_tc27_pipeline_status(client):
    """/pipeline/status returns a DAG with the three stages and a summary."""
    st = client.get("/pipeline/status").json()
    assert {"ingest", "preprocess", "train"} <= set(st["dag"]["nodes"])
    assert {"success", "failed", "total"} <= set(st["summary"])


def test_tc28_template_csv(client):
    """Template CSV has the expected header."""
    assert client.get("/template.csv").text.startswith("City,Date,PM2.5,PM10,NO2,SO2,CO,O3")


def _upload(client, text, name="t.csv"):
    return client.post("/predict/batch", files={"file": (name, io.BytesIO(text.encode()), "text/csv")})


def test_tc29_batch_happy_path(client):
    """Template file predicts every row."""
    b = _upload(client, client.get("/template.csv").text).json()
    assert b["total"] == 2 and b["succeeded"] == 2 and b["failed"] == 0


def test_tc30_batch_partial_failure(client):
    """Bad rows are reported by row number; good rows still succeed."""
    csv = ("City,Date,PM2.5,PM10,NO2,SO2,CO,O3\nDelhi,2026-01-01,150,300,,,,\n"
           "Nowhere,2026-01-01,50,90,,,,\nDelhi,2026-01-01,-5,90,,,,\n")
    b = _upload(client, csv).json()
    assert (b["succeeded"], b["failed"]) == (1, 2) and {e["row"] for e in b["errors"]} == {3, 4}


def test_tc31_batch_missing_city_column(client):
    """CSV without City -> 400 with clear message."""
    r = _upload(client, "PM2.5,PM10\n10,20\n")
    assert r.status_code == 400 and "City" in r.json()["message"]


def test_tc32_batch_no_pollutant_columns(client):
    """CSV with City only -> 400."""
    assert _upload(client, "City\nDelhi\n").status_code == 400


def test_tc33_batch_empty_and_garbage(client):
    """Header-only and binary files are rejected, not crashed on."""
    assert _upload(client, "City,PM2.5,PM10\n").status_code == 400
    r = client.post("/predict/batch", files={"file": ("x.csv", b"\x00\x01\x02\xff", "text/csv")})
    assert r.status_code == 400


def test_tc34_metrics_endpoint_counts(client, valid_payload):
    """Prometheus endpoint exposes request, prediction and drift metrics."""
    client.post("/predict", json=valid_payload)
    text = client.get("/metrics").text
    for name in ["airsense_http_requests_total", "airsense_predictions_total",
                 "airsense_http_request_seconds_bucket", "airsense_input_drift_zscore",
                 "airsense_model_loaded 1.0", "airsense_errors_total"]:
        assert name in text


def test_tc44_model_unavailable_returns_503(client, valid_payload, monkeypatch):
    """If the model cannot be loaded, /predict gives 503 (not 500) and /health says degraded."""
    from backend import config as settings
    from backend import main
    monkeypatch.setitem(main._state, "predictor", None)
    monkeypatch.setattr(settings, "META_PATH", "/nonexistent/meta.json")
    r = client.post("/predict", json=valid_payload)
    assert r.status_code == 503 and r.json()["error"] == "model_unavailable"
    assert client.get("/health").json() == {"status": "degraded", "model_loaded": False}


def test_tc45_batch_metrics_exposed(client):
    """Batch processing increments the ok/failed row counters in /metrics."""
    _upload(client, "City,PM2.5,PM10\nDelhi,100,200\nNowhere,1,2\n")
    text = client.get("/metrics").text
    assert 'airsense_batch_rows_total{outcome="ok"}' in text and 'airsense_batch_rows_total{outcome="failed"}' in text
