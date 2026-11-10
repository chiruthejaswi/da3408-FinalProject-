"""Shared fixtures. Tests run against the real trained model (run `dvc repro` first)."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="session")
def client():
    """FastAPI test client with the model loaded."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def valid_payload():
    """A minimal valid /predict body."""
    return {"city": "Delhi", "pm25": 180, "pm10": 320, "no2": 60, "so2": 15, "co": 2.5, "o3": 40}
