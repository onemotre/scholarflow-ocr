import httpx
import pytest

from scholarflow_ocr.config import load_config
from scholarflow_ocr.ocr.client import BaiduOCRClient, OCRError
from scholarflow_ocr.ocr.models import parse_result_from_json


def _mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/oauth/2.0/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 2592000})
        if path.endswith("/paddle-vl-parser/task"):
            return httpx.Response(200, json={"error_code": 0, "result": {"task_id": "T1"}})
        if path.endswith("/paddle-vl-parser/task/query"):
            return httpx.Response(200, json={
                "error_code": 0,
                "result": {"status": "success", "parse_result_url": "https://files/result.json"},
            })
        if str(request.url) == "https://files/result.json":
            return httpx.Response(200, json={
                "pages": [{
                    "page_num": 1,
                    "meta": {"page_width": 1000, "page_height": 1400},
                    "layouts": [{"layout_id": 1, "type": "title", "text": "Hello",
                                 "position": [10, 20, 100, 30]}],
                }],
            })
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_parse_returns_result(monkeypatch):
    cfg = load_config()
    client = BaiduOCRClient(cfg, client=httpx.Client(transport=_mock_transport()))
    result = client.parse(b"%PDF-1.4 fake", "paper.pdf")
    assert len(result.pages) == 1
    assert result.pages[0].width_px == 1000
    assert result.pages[0].layouts[0].type == "title"
    assert result.pages[0].layouts[0].position == (10.0, 20.0, 100.0, 30.0)


def test_submit_error_raises(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/oauth/2.0/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(200, json={"error_code": 216100, "error_msg": "invalid param"})
    cfg = load_config()
    client = BaiduOCRClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OCRError):
        client.parse(b"x", "p.pdf")


def test_parse_result_from_json_empty():
    assert parse_result_from_json({}).pages == ()


def test_http_status_error_raises_ocrerror():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/2.0/token"):
            return httpx.Response(500, json={"error": "internal server error"})
        return httpx.Response(404)

    cfg = load_config()
    client = BaiduOCRClient(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OCRError):
        client.parse(b"x", "p.pdf")
