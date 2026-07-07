from fastapi.testclient import TestClient

from scholarflow_ocr.api import create_app
from scholarflow_ocr.ocr.fake import FakeOCRClient
from scholarflow_ocr.ocr.models import LayoutBox, Page, ParseResult


def _fake_result() -> ParseResult:
    return ParseResult((Page(1, 1000, 1400, (
        LayoutBox(1, "title", "API Paper", (0, 0, 400, 30)),
        LayoutBox(2, "title", "1 Intro", (0, 100, 300, 20)),
        LayoutBox(3, "text", "Some text.", (0, 130, 400, 40)),
    )),))


def _client(monkeypatch):
    # Avoid reading real PDF geometry: stub sizes_fn to a fixed page size.
    app = create_app(ocr_client=FakeOCRClient(_fake_result()), sizes_fn=lambda pdf: [(500.0, 700.0)])
    return TestClient(app)


def test_health(monkeypatch):
    resp = _client(monkeypatch).get("/health")
    assert resp.status_code == 200


def test_process_returns_tei(monkeypatch):
    resp = _client(monkeypatch).post(
        "/api/processFulltextDocument",
        files={"input": ("paper.pdf", b"%PDF-1.4 x", "application/pdf")},
        data={"teiCoordinates": "figure"},
    )
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "<title>API Paper</title>" in resp.text
    assert 'n="1"' in resp.text


def test_process_missing_file_returns_400(monkeypatch):
    resp = _client(monkeypatch).post("/api/processFulltextDocument", data={"x": "y"})
    assert resp.status_code == 400
