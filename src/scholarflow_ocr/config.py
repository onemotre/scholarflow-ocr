import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    app_id: str
    api_key: str
    secret_key: str
    ocr_endpoint: str
    poll_timeout_seconds: int
    poll_interval_seconds: int
    http_port: int
    max_upload_bytes: int


def _require(key: str) -> str:
    value = os.environ.get(key, "")
    if not value:
        raise RuntimeError(f"missing required env: {key}")
    return value


def load_config() -> Config:
    return Config(
        app_id=os.environ.get("BAIDU_OCR_APP_ID", ""),
        api_key=_require("BAIDU_OCR_API_KEY"),
        secret_key=_require("BAIDU_OCR_SECRET_KEY"),
        ocr_endpoint=os.environ.get("BAIDU_OCR_ENDPOINT", "https://aip.baidubce.com").rstrip("/"),
        poll_timeout_seconds=int(os.environ.get("OCR_POLL_TIMEOUT_SECONDS", "300")),
        poll_interval_seconds=int(os.environ.get("OCR_POLL_INTERVAL_SECONDS", "3")),
        http_port=int(os.environ.get("HTTP_PORT", "8070")),
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", "33554432")),
    )
