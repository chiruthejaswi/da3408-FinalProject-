"""UI tests with Streamlit's AppTest against a MOCKED backend (TC-35 .. TC-42)."""
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
sys.path.insert(0, str(FRONT))

import api_client  # noqa: E402
from api_client import ApiClient, ApiError, ApiUnavailable  # noqa: E402

RESULT = {"city": "Delhi", "category": "Very Poor", "confidence": 0.93, "color": "#FF0000",
          "headline": "Air quality is very poor", "advice": "Avoid outdoor exercise.",
          "sensitive_groups": "Stay indoors.", "imputed_fields": ["SO2"], "low_confidence": False,
          "probabilities": {"Good": 0, "Satisfactory": 0, "Moderate": 0.02, "Poor": 0.05,
                            "Very Poor": 0.93, "Severe": 0}}


@pytest.fixture()
def mock_api(monkeypatch):
    """Patch ApiClient methods so no server is needed."""
    monkeypatch.setattr(ApiClient, "health", lambda self: {"model_loaded": True})
    monkeypatch.setattr(ApiClient, "cities", lambda self: ["Chennai", "Delhi", "Mumbai"])
    monkeypatch.setattr(ApiClient, "predict", lambda self, p: RESULT)
    monkeypatch.setattr(ApiClient, "template_csv", lambda self: "City,PM2.5\n")


def run_app():
    at = AppTest.from_file(str(FRONT / "app.py"), default_timeout=20)
    return at.run()


def test_tc35_predict_page_renders(mock_api):
    """Predict page shows title, city dropdown and 6 reading inputs."""
    load = run_app()
    assert not load.exception
    assert len(load.number_input) == 6 and load.selectbox[0].options == ["Chennai", "Delhi", "Mumbai"]


def test_tc36_example_button_fills_form(mock_api):
    """Clicking an example fills city and readings."""
    at = run_app()
    at.button[1].click().run()  # second example: "Typical metro day"
    assert at.session_state["pm25"] == 55.0 and at.session_state["city"] == "Mumbai"


def test_tc37_too_few_readings_warns(mock_api):
    """Predict with 0 readings -> friendly warning, no API call."""
    at = run_app()
    at.button[-1].click().run()
    assert any("at least 2" in w.value for w in at.warning)


def test_tc38_successful_prediction_shown(mock_api):
    """Two readings -> result card with category and confidence."""
    at = run_app()
    at.number_input[0].set_value(200.0)
    at.number_input[1].set_value(350.0)
    at.button[-1].click().run()
    assert not at.exception
    assert any("Very Poor" in m.value for m in at.markdown)


def test_tc39_service_down_message(mock_api, monkeypatch):
    """Backend unreachable -> readable error, no stack trace."""
    def boom(self, p):
        raise ApiUnavailable("down")
    monkeypatch.setattr(ApiClient, "predict", boom)
    at = run_app()
    at.number_input[0].set_value(200.0)
    at.number_input[1].set_value(350.0)
    at.button[-1].click().run()
    assert not at.exception and any("isn't responding" in e.value for e in at.error)


def test_tc40_api_validation_error_listed(mock_api, monkeypatch):
    """422 from the API is shown with field-level details."""
    def bad(self, p):
        raise ApiError(422, "Some inputs are invalid.", [{"field": "pm25", "message": "too big"}])
    monkeypatch.setattr(ApiClient, "predict", bad)
    at = run_app()
    at.number_input[0].set_value(200.0)
    at.number_input[1].set_value(350.0)
    at.button[-1].click().run()
    assert any("invalid" in e.value for e in at.error)


def test_tc41_api_client_unavailable_maps_exception(monkeypatch):
    """Connection errors become ApiUnavailable."""
    import requests

    def fail(*a, **k):
        raise requests.ConnectionError("nope")
    monkeypatch.setattr(api_client.requests, "request", fail)
    with pytest.raises(ApiUnavailable):
        ApiClient("http://x").cities()


def test_tc42_api_url_is_configurable(monkeypatch):
    """API_URL env var controls the backend address (loose coupling)."""
    monkeypatch.setenv("API_URL", "http://backend:9999/")
    assert ApiClient().base_url == "http://backend:9999"


def test_tc43_example_skips_unknown_city(mock_api):
    """An example whose city the model lacks keeps the current city but fills readings."""
    at = run_app()
    at.button[0].click().run()  # Aizawl is NOT in the mocked city list
    assert at.session_state["city"] in ["Chennai", "Delhi", "Mumbai"] and at.session_state["pm25"] == 12.0
