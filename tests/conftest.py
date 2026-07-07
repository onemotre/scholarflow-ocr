import pytest


@pytest.fixture(autouse=True)
def _ocr_env(monkeypatch):
    monkeypatch.setenv("BAIDU_OCR_API_KEY", "test-key")
    monkeypatch.setenv("BAIDU_OCR_SECRET_KEY", "test-secret")
