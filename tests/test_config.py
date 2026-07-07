import pytest
from scholarflow_ocr.config import load_config, Config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("BAIDU_OCR_API_KEY", "k")
    monkeypatch.setenv("BAIDU_OCR_SECRET_KEY", "s")
    monkeypatch.setenv("HTTP_PORT", "9000")
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.api_key == "k"
    assert cfg.secret_key == "s"
    assert cfg.http_port == 9000
    assert cfg.ocr_endpoint == "https://aip.baidubce.com"


def test_load_config_missing_secret_raises(monkeypatch):
    monkeypatch.delenv("BAIDU_OCR_API_KEY", raising=False)
    monkeypatch.delenv("BAIDU_OCR_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        load_config()
