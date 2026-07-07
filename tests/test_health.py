from fastapi.testclient import TestClient
from scholarflow_ocr.api import create_app


def test_health_ok():
    resp = TestClient(create_app()).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_isalive_true():
    resp = TestClient(create_app()).get("/api/isalive")
    assert resp.status_code == 200
    assert resp.text == "true"
