# scholarflow-ocr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small Python service that impersonates GROBID's `POST /api/processFulltextDocument`, converting a PDF into the TEI XML subset `scholarflow-server` consumes by calling Baidu PaddleOCR-VL and structuring its layout output deterministically (no LLM).

**Architecture:** A FastAPI app receives the multipart PDF, reads page point-sizes with pypdf, submits the PDF to PaddleOCR-VL (async submit→poll→fetch), maps the returned layout JSON into an internal `Document` model (front-matter, sections, figures, references), translates pixel boxes to PDF points, and renders TEI. The service owns no database, no storage, and no figure cropping — the server keeps doing those from the `@coords` we emit.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx, pypdf, lxml, pytest.

## Global Constraints

- Python 3.12; target Docker image < 200 MB; runtime must fit 2 cores / 2 GB RAM (no local ML, no PDF rasterization).
- No LLM calls anywhere. All structuring is deterministic/heuristic.
- Secrets (`BAIDU_OCR_API_KEY`, `BAIDU_OCR_SECRET_KEY`, `BAIDU_OCR_APP_ID`) come from env only; never hardcoded, never committed. `.env` is gitignored.
- Package name: `scholarflow_ocr` (underscore, Python import path); repo/dir: `scholarflow-ocr` (hyphen).
- TEI is emitted **without an XML namespace**. This is server-compatible because the server's `grobid.go` struct tags carry no namespace, so Go's `encoding/xml` matches purely by local element name.
- The TEI must populate exactly the paths the server reads (see Task 8 contract). Anything else is out of scope.
- Default service port: **8070** (GROBID's default, so the server's `GROBID_URL` barely changes).
- All work happens in the worktree at `scholarflow-ocr/.worktrees/build` on branch `feat/ocr-parser`. All paths below are relative to that worktree root.

---

## File Structure

```
pyproject.toml                         # deps + pytest config
.env.example                           # committed template (no real secrets)
Dockerfile
docker-compose.yml
README.md                              # updated with runbook
src/scholarflow_ocr/
  __init__.py
  config.py                            # env → Config
  main.py                              # uvicorn entrypoint
  api.py                               # FastAPI app + GROBID-compatible routes
  pdfmeta.py                           # PDF page sizes in points (pypdf)
  ocr/
    __init__.py
    models.py                          # ParseResult / Page / LayoutBox
    client.py                          # BaiduOCRClient: auth, submit, poll, fetch
    fake.py                            # FakeOCRClient for tests
  parse/
    __init__.py
    coords.py                          # Coords + pixel→point translate()
    document.py                        # Document model (frozen dataclasses)
    text.py                            # shared helpers (split_name, normalize)
    layout.py                          # layouts → body sections + figures
    frontmatter.py                     # title/abstract/authors/doi/year
    references.py                      # heuristic bibliography parser
    pipeline.py                        # ParseResult + page sizes → Document
  tei/
    __init__.py
    render.py                          # Document → TEI XML
scripts/
  capture_fixture.py                   # run real API on a sample PDF → save fixture
tests/
  conftest.py
  fixtures/
    sample_parse_result.json           # captured from Task 2
  test_config.py
  test_ocr_client.py
  test_pdfmeta.py
  test_coords.py
  test_layout.py
  test_frontmatter.py
  test_references.py
  test_pipeline.py
  test_tei_render.py
  test_contract.py
  test_api.py
```

---

## Task 1: Project scaffold, config, health endpoint

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/scholarflow_ocr/__init__.py`, `src/scholarflow_ocr/config.py`, `src/scholarflow_ocr/api.py`, `src/scholarflow_ocr/main.py`
- Test: `tests/test_config.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `Config` frozen dataclass with fields `app_id, api_key, secret_key, ocr_endpoint, poll_timeout_seconds, poll_interval_seconds, http_port, max_upload_bytes`; `load_config() -> Config` (raises `RuntimeError` if a required secret is missing). `create_app() -> FastAPI` exposing `GET /health` → `{"status":"ok"}` and `GET /api/isalive` → `true`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "scholarflow-ocr"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "httpx>=0.27",
    "pypdf>=4.2",
    "lxml>=5.2",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Write `.env.example`**

```bash
# Copy to .env and fill in. .env is gitignored.
BAIDU_OCR_APP_ID=
BAIDU_OCR_API_KEY=
BAIDU_OCR_SECRET_KEY=
BAIDU_OCR_ENDPOINT=https://aip.baidubce.com
HTTP_PORT=8070
OCR_POLL_TIMEOUT_SECONDS=300
OCR_POLL_INTERVAL_SECONDS=3
MAX_UPLOAD_BYTES=33554432
```

- [ ] **Step 3: Write the failing test** `tests/test_config.py`

```python
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
```

- [ ] **Step 4: Run it, verify it fails**

Run: `cd scholarflow-ocr/.worktrees/build && python -m pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: scholarflow_ocr.config`).

- [ ] **Step 5: Implement `src/scholarflow_ocr/__init__.py`** (empty file) and `src/scholarflow_ocr/config.py`

```python
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
```

- [ ] **Step 6: Run test, verify pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Write `src/scholarflow_ocr/api.py`** (health only for now; the parse route is added in Task 9)

```python
from fastapi import FastAPI, Response


def create_app() -> FastAPI:
    app = FastAPI(title="scholarflow-ocr")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/isalive")
    def isalive() -> Response:
        # GROBID returns the literal `true`; mirror it.
        return Response(content="true", media_type="text/plain")

    return app
```

- [ ] **Step 8: Write `src/scholarflow_ocr/main.py`**

```python
import uvicorn

from scholarflow_ocr.api import create_app
from scholarflow_ocr.config import load_config

app = create_app()


def main() -> None:
    cfg = load_config()
    uvicorn.run(app, host="0.0.0.0", port=cfg.http_port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Write `tests/conftest.py`** (ensures a clean env baseline for tests)

```python
import pytest


@pytest.fixture(autouse=True)
def _ocr_env(monkeypatch):
    monkeypatch.setenv("BAIDU_OCR_API_KEY", "test-key")
    monkeypatch.setenv("BAIDU_OCR_SECRET_KEY", "test-secret")
```

- [ ] **Step 10: Install deps and run the full suite**

Run: `python -m pip install -e '.[dev]' && python -m pytest -v`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml .env.example src/scholarflow_ocr/__init__.py src/scholarflow_ocr/config.py src/scholarflow_ocr/api.py src/scholarflow_ocr/main.py tests/test_config.py tests/conftest.py
git commit -m "feat: scaffold service with config and health endpoint"
```

---

## Task 2: PaddleOCR-VL client + models + real-response fixture

**Files:**
- Create: `src/scholarflow_ocr/ocr/__init__.py`, `src/scholarflow_ocr/ocr/models.py`, `src/scholarflow_ocr/ocr/client.py`, `src/scholarflow_ocr/ocr/fake.py`, `scripts/capture_fixture.py`
- Test: `tests/test_ocr_client.py`

**Interfaces:**
- Produces:
  - `LayoutBox(layout_id:int, type:str, text:str, position:tuple[float,float,float,float], sub_type:str)`
  - `Page(page_num:int, width_px:float, height_px:float, layouts:tuple[LayoutBox,...])`
  - `ParseResult(pages:tuple[Page,...])`
  - `parse_result_from_json(data:dict) -> ParseResult`
  - `OCRClient` protocol with `parse(pdf:bytes, file_name:str) -> ParseResult`
  - `BaiduOCRClient(cfg, client:httpx.Client|None=None)` implementing it; raises `OCRError` on failure.
  - `FakeOCRClient(result:ParseResult)` implementing it (returns the canned result).

- [ ] **Step 1: Write `src/scholarflow_ocr/ocr/__init__.py`** (empty file)

- [ ] **Step 2: Write `src/scholarflow_ocr/ocr/models.py`**

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LayoutBox:
    layout_id: int
    type: str
    text: str
    position: tuple[float, float, float, float]  # x, y, w, h (pixels)
    sub_type: str = ""


@dataclass(frozen=True)
class Page:
    page_num: int
    width_px: float
    height_px: float
    layouts: tuple[LayoutBox, ...]


@dataclass(frozen=True)
class ParseResult:
    pages: tuple[Page, ...]


class OCRClient(Protocol):
    def parse(self, pdf: bytes, file_name: str) -> ParseResult: ...


def _position(raw: object) -> tuple[float, float, float, float]:
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    return (0.0, 0.0, 0.0, 0.0)


def parse_result_from_json(data: dict) -> ParseResult:
    pages: list[Page] = []
    for p in data.get("pages", []) or []:
        meta = p.get("meta", {}) or {}
        layouts = tuple(
            LayoutBox(
                layout_id=int(lay.get("layout_id", 0) or 0),
                type=str(lay.get("type", "") or ""),
                text=str(lay.get("text", "") or ""),
                position=_position(lay.get("position")),
                sub_type=str(lay.get("sub_type", "") or ""),
            )
            for lay in (p.get("layouts", []) or [])
        )
        pages.append(
            Page(
                page_num=int(p.get("page_num", p.get("page_id", 0)) or 0),
                width_px=float(meta.get("page_width", 0) or 0),
                height_px=float(meta.get("page_height", 0) or 0),
                layouts=layouts,
            )
        )
    return ParseResult(pages=tuple(pages))
```

- [ ] **Step 3: Write the failing test** `tests/test_ocr_client.py`

```python
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
```

- [ ] **Step 4: Run it, verify it fails**

Run: `python -m pytest tests/test_ocr_client.py -v`
Expected: FAIL (`ModuleNotFoundError: scholarflow_ocr.ocr.client`).

- [ ] **Step 5: Implement `src/scholarflow_ocr/ocr/client.py`**

```python
import base64
import time

import httpx

from scholarflow_ocr.config import Config
from scholarflow_ocr.ocr.models import ParseResult, parse_result_from_json


class OCRError(Exception):
    pass


class BaiduOCRClient:
    def __init__(self, cfg: Config, client: httpx.Client | None = None) -> None:
        self._cfg = cfg
        self._http = client or httpx.Client(timeout=60)

    def parse(self, pdf: bytes, file_name: str) -> ParseResult:
        token = self._access_token()
        task_id = self._submit(token, pdf, file_name)
        result_url = self._poll(token, task_id)
        return parse_result_from_json(self._fetch_json(result_url))

    def _base(self) -> str:
        return self._cfg.ocr_endpoint

    def _access_token(self) -> str:
        resp = self._http.post(
            f"{self._base()}/oauth/2.0/token",
            params={
                "grant_type": "client_credentials",
                "client_id": self._cfg.api_key,
                "client_secret": self._cfg.secret_key,
            },
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise OCRError("no access_token in oauth response")
        return token

    def _submit(self, token: str, pdf: bytes, file_name: str) -> str:
        resp = self._http.post(
            f"{self._base()}/rest/2.0/brain/online/v2/paddle-vl-parser/task",
            params={"access_token": token},
            data={"file_data": base64.b64encode(pdf).decode("ascii"), "file_name": file_name},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error_code"):
            raise OCRError(f"submit failed: {body.get('error_code')} {body.get('error_msg')}")
        task_id = (body.get("result") or {}).get("task_id")
        if not task_id:
            raise OCRError("submit returned no task_id")
        return task_id

    def _poll(self, token: str, task_id: str) -> str:
        deadline = time.monotonic() + self._cfg.poll_timeout_seconds
        while True:
            resp = self._http.post(
                f"{self._base()}/rest/2.0/brain/online/v2/paddle-vl-parser/task/query",
                params={"access_token": token},
                data={"task_id": task_id},
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("error_code"):
                raise OCRError(f"query failed: {body.get('error_code')} {body.get('error_msg')}")
            result = body.get("result") or {}
            status = result.get("status")
            if status == "success":
                url = result.get("parse_result_url")
                if not url:
                    raise OCRError("success but no parse_result_url")
                return url
            if status == "failed":
                raise OCRError(f"task failed: {result.get('task_error')}")
            if time.monotonic() >= deadline:
                raise OCRError("polling timed out")
            time.sleep(self._cfg.poll_interval_seconds)

    def _fetch_json(self, url: str) -> dict:
        resp = self._http.get(url)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 6: Implement `src/scholarflow_ocr/ocr/fake.py`**

```python
from scholarflow_ocr.ocr.models import ParseResult


class FakeOCRClient:
    def __init__(self, result: ParseResult) -> None:
        self._result = result

    def parse(self, pdf: bytes, file_name: str) -> ParseResult:
        return self._result
```

- [ ] **Step 7: Run tests, verify pass**

Run: `python -m pytest tests/test_ocr_client.py -v`
Expected: PASS (three tests).

- [ ] **Step 8: Write `scripts/capture_fixture.py`** (used once, against the real API, to pin field/type values)

```python
"""Run the real PaddleOCR-VL API on a sample PDF and save the parse result.

Usage: python scripts/capture_fixture.py path/to/sample.pdf
Requires a populated .env (loaded by the caller's shell) with real credentials.
Writes tests/fixtures/sample_parse_result.json.
"""
import json
import sys
from pathlib import Path

import httpx

from scholarflow_ocr.config import load_config
from scholarflow_ocr.ocr.client import BaiduOCRClient


def main() -> None:
    pdf_path = Path(sys.argv[1])
    cfg = load_config()
    client = BaiduOCRClient(cfg, client=httpx.Client(timeout=120))
    token = client._access_token()
    task_id = client._submit(token, pdf_path.read_bytes(), pdf_path.name)
    url = client._poll(token, task_id)
    raw = client._fetch_json(url)
    out = Path("tests/fixtures/sample_parse_result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"wrote {out} ({len(raw.get('pages', []))} pages)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Capture a real fixture** (manual, needs real creds + a small sample PDF)

Run:
```bash
set -a && source .env && set +a
python scripts/capture_fixture.py tests/fixtures/sample.pdf
```
Expected: writes `tests/fixtures/sample_parse_result.json`. **Inspect it** and confirm the actual `type` string values (e.g. `title`, `text`, `image`, `table`). If they differ from the assumptions in Task 4, update the `LAYOUT_*` sets there — this fixture is the source of truth.

> If real credentials or a sample PDF are unavailable at this step, hand-write a minimal `tests/fixtures/sample_parse_result.json` with 1–2 pages covering a title, an abstract, one numbered section with a paragraph, one image, and a references block, using the JSON shape from Step 5's test. Replace it with a real capture before shipping.

- [ ] **Step 10: Commit**

```bash
git add src/scholarflow_ocr/ocr scripts/capture_fixture.py tests/test_ocr_client.py tests/fixtures
git commit -m "feat: add PaddleOCR-VL client, models, and response fixture"
```

---

## Task 3: PDF page sizes + coordinate translation

**Files:**
- Create: `src/scholarflow_ocr/pdfmeta.py`, `src/scholarflow_ocr/parse/__init__.py`, `src/scholarflow_ocr/parse/coords.py`
- Test: `tests/test_pdfmeta.py`, `tests/test_coords.py`

**Interfaces:**
- Produces:
  - `page_point_sizes(pdf:bytes) -> list[tuple[float,float]]` (per-page `(width_pt, height_pt)`).
  - `Coords(page:int, x:float, y:float, w:float, h:float)` with `.tei() -> str` → `"page,x,y,w,h"` (2 decimals).
  - `translate(page:int, box:tuple[float,float,float,float], w_px:float, h_px:float, w_pt:float, h_pt:float) -> Coords | None` (None if any dimension ≤ 0).

- [ ] **Step 1: Write the failing test** `tests/test_coords.py`

```python
from scholarflow_ocr.parse.coords import Coords, translate


def test_translate_scales_pixels_to_points():
    # image is 1000x1400 px; page is 500x700 pt → scale 0.5 on both axes
    c = translate(2, (100, 200, 300, 40), w_px=1000, h_px=1400, w_pt=500, h_pt=700)
    assert c == Coords(2, 50.0, 100.0, 150.0, 20.0)


def test_translate_zero_dimension_returns_none():
    assert translate(1, (0, 0, 10, 10), w_px=0, h_px=1400, w_pt=500, h_pt=700) is None


def test_coords_tei_format():
    assert Coords(3, 12.345, 6.0, 7.5, 8.0).tei() == "3,12.35,6.00,7.50,8.00"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_coords.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/scholarflow_ocr/parse/__init__.py`** (empty) and `src/scholarflow_ocr/parse/coords.py`

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Coords:
    page: int
    x: float
    y: float
    w: float
    h: float

    def tei(self) -> str:
        return f"{self.page},{self.x:.2f},{self.y:.2f},{self.w:.2f},{self.h:.2f}"


def translate(
    page: int,
    box: tuple[float, float, float, float],
    w_px: float,
    h_px: float,
    w_pt: float,
    h_pt: float,
) -> Coords | None:
    if w_px <= 0 or h_px <= 0 or w_pt <= 0 or h_pt <= 0:
        return None
    sx = w_pt / w_px
    sy = h_pt / h_px
    x, y, w, h = box
    return Coords(page, x * sx, y * sy, w * sx, h * sy)
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_coords.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing test** `tests/test_pdfmeta.py`

```python
from scholarflow_ocr.pdfmeta import page_point_sizes


def _one_page_pdf() -> bytes:
    # Minimal single-page PDF, MediaBox 612x792 (US Letter).
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
    )


def test_page_point_sizes():
    sizes = page_point_sizes(_one_page_pdf())
    assert sizes == [(612.0, 792.0)]
```

- [ ] **Step 6: Run it, verify it fails**

Run: `python -m pytest tests/test_pdfmeta.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 7: Implement `src/scholarflow_ocr/pdfmeta.py`**

```python
import io

from pypdf import PdfReader


def page_point_sizes(pdf: bytes) -> list[tuple[float, float]]:
    reader = PdfReader(io.BytesIO(pdf))
    sizes: list[tuple[float, float]] = []
    for page in reader.pages:
        box = page.mediabox
        sizes.append((float(box.width), float(box.height)))
    return sizes
```

- [ ] **Step 8: Run test, verify pass**

Run: `python -m pytest tests/test_pdfmeta.py -v`
Expected: PASS. (If pypdf rejects the hand-written PDF, replace `_one_page_pdf()` with a tiny real PDF committed under `tests/fixtures/onepage.pdf` and read it instead.)

- [ ] **Step 9: Commit**

```bash
git add src/scholarflow_ocr/pdfmeta.py src/scholarflow_ocr/parse/__init__.py src/scholarflow_ocr/parse/coords.py tests/test_pdfmeta.py tests/test_coords.py
git commit -m "feat: add pdf page sizing and coordinate translation"
```

---

## Task 4: Document model, shared text helpers, layout → sections/figures

**Files:**
- Create: `src/scholarflow_ocr/parse/document.py`, `src/scholarflow_ocr/parse/text.py`, `src/scholarflow_ocr/parse/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Produces:
  - `document.py`: `Author(forename,surname)`, `Paragraph(text, coords:Coords|None)`, `Section(number:str, heading:str, paragraphs:tuple[Paragraph,...], coords:Coords|None)`, `Figure(kind:str, label:str, caption:str, coords:Coords|None)`, `Reference(order:int, title:str, authors:tuple[str,...], venue:str, year:str, doi:str, raw_text:str)`, `Document(title, abstract, doi, year, authors, sections, figures, references)` (all defaults empty).
  - `text.py`: `split_name(name:str) -> tuple[str,str]` (forename, surname), `normalize(s:str) -> str` (collapse whitespace).
  - `layout.py`: `LAYOUT_TITLE:set[str]`, `LAYOUT_TEXT:set[str]`, `LAYOUT_FIGURE:set[str]`; `section_number(heading:str) -> tuple[str,str]` (number, rest); `build_body(page:Page, sizes, base_order:int) -> tuple[list[Section], list[Figure], int]` where `sizes` is `list[tuple[float,float]]` of page point dims.
- Consumes: `Page`/`LayoutBox` (Task 2), `Coords`/`translate` (Task 3).

- [ ] **Step 1: Write `src/scholarflow_ocr/parse/document.py`**

```python
from dataclasses import dataclass, field

from scholarflow_ocr.parse.coords import Coords


@dataclass(frozen=True)
class Author:
    forename: str
    surname: str


@dataclass(frozen=True)
class Paragraph:
    text: str
    coords: Coords | None = None


@dataclass(frozen=True)
class Section:
    number: str
    heading: str
    paragraphs: tuple[Paragraph, ...] = ()
    coords: Coords | None = None


@dataclass(frozen=True)
class Figure:
    kind: str  # "figure" | "table"
    label: str
    caption: str
    coords: Coords | None = None


@dataclass(frozen=True)
class Reference:
    order: int
    title: str = ""
    authors: tuple[str, ...] = ()
    venue: str = ""
    year: str = ""
    doi: str = ""
    raw_text: str = ""


@dataclass(frozen=True)
class Document:
    title: str = ""
    abstract: str = ""
    doi: str = ""
    year: str = ""
    authors: tuple[Author, ...] = ()
    sections: tuple[Section, ...] = ()
    figures: tuple[Figure, ...] = ()
    references: tuple[Reference, ...] = ()
```

- [ ] **Step 2: Write `src/scholarflow_ocr/parse/text.py`**

```python
import re

_WS = re.compile(r"\s+")


def normalize(s: str) -> str:
    return _WS.sub(" ", (s or "").strip())


def split_name(name: str) -> tuple[str, str]:
    """Split a display name into (forename, surname). Last token is the surname."""
    parts = normalize(name).split(" ")
    if not parts or parts == [""]:
        return ("", "")
    if len(parts) == 1:
        return ("", parts[0])
    return (" ".join(parts[:-1]), parts[-1])
```

- [ ] **Step 3: Write the failing test** `tests/test_layout.py`

```python
from scholarflow_ocr.ocr.models import LayoutBox, Page
from scholarflow_ocr.parse.layout import build_body, section_number
from scholarflow_ocr.parse.text import split_name


def test_section_number_splits_leading_numbering():
    assert section_number("2.1 Motion Track") == ("2.1", "Motion Track")
    assert section_number("Introduction") == ("", "Introduction")


def test_split_name():
    assert split_name("Jane Q Public") == ("Jane Q", "Public")
    assert split_name("Plato") == ("", "Plato")


def test_build_body_makes_sections_and_figures():
    page = Page(
        page_num=1,
        width_px=1000,
        height_px=1400,
        layouts=(
            LayoutBox(1, "title", "2 Method", (0, 100, 200, 20)),
            LayoutBox(2, "text", "We do things.", (0, 130, 400, 40)),
            LayoutBox(3, "image", "Figure 1: our pipeline.", (0, 200, 300, 300)),
        ),
    )
    sizes = [(500.0, 700.0)]  # scale 0.5
    sections, figures, next_order = build_body(page, sizes, base_order=0)
    assert len(sections) == 1
    assert sections[0].number == "2"
    assert sections[0].heading == "Method"
    assert sections[0].paragraphs[0].text == "We do things."
    assert sections[0].coords is not None and sections[0].coords.page == 1
    assert len(figures) == 1
    assert figures[0].kind == "figure"
    assert figures[0].label == "Figure 1"
    assert figures[0].caption == "Figure 1: our pipeline."
    assert next_order == 1
```

- [ ] **Step 4: Run it, verify it fails**

Run: `python -m pytest tests/test_layout.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 5: Implement `src/scholarflow_ocr/parse/layout.py`**

```python
import re

from scholarflow_ocr.ocr.models import LayoutBox, Page
from scholarflow_ocr.parse.coords import Coords, translate
from scholarflow_ocr.parse.document import Figure, Paragraph, Section
from scholarflow_ocr.parse.text import normalize

# Layout type strings from PaddleOCR-VL. Confirm/extend against the captured
# fixture (Task 2, Step 9); unknown types are ignored.
LAYOUT_TITLE = {"title", "paragraph_title", "doc_title"}
LAYOUT_TEXT = {"text", "paragraph", "plain_text"}
LAYOUT_FIGURE = {"image", "figure", "table", "chart"}
_TABLE_TYPES = {"table"}

_NUM = re.compile(r"^(\d+(?:\.\d+)*)\s+(.*)$")
_FIG_LABEL = re.compile(r"^((?:figure|fig\.?|table)\s*\d+)", re.IGNORECASE)


def section_number(heading: str) -> tuple[str, str]:
    m = _NUM.match(normalize(heading))
    if m:
        return (m.group(1), m.group(2).strip())
    return ("", normalize(heading))


def _coords(page: Page, box: LayoutBox, sizes: list[tuple[float, float]]) -> Coords | None:
    idx = page.page_num - 1
    if idx < 0 or idx >= len(sizes):
        return None
    w_pt, h_pt = sizes[idx]
    return translate(page.page_num, box.position, page.width_px, page.height_px, w_pt, h_pt)


def _figure_label(caption: str, fallback_n: int, kind: str) -> str:
    m = _FIG_LABEL.match(normalize(caption))
    if m:
        return m.group(1)
    return f"{'Table' if kind == 'table' else 'Figure'} {fallback_n}"


def build_body(
    page: Page, sizes: list[tuple[float, float]], base_order: int
) -> tuple[list[Section], list[Figure], int]:
    sections: list[Section] = []
    figures: list[Figure] = []
    order = base_order
    cur_number = ""
    cur_heading = ""
    cur_coords: Coords | None = None
    cur_paras: list[Paragraph] = []

    def flush() -> None:
        nonlocal cur_number, cur_heading, cur_coords, cur_paras
        if cur_heading or cur_paras:
            sections.append(Section(cur_number, cur_heading, tuple(cur_paras), cur_coords))
        cur_number, cur_heading, cur_coords, cur_paras = "", "", None, []

    for box in page.layouts:
        if box.type in LAYOUT_TITLE:
            flush()
            cur_number, cur_heading = section_number(box.text)
            cur_coords = _coords(page, box, sizes)
        elif box.type in LAYOUT_TEXT:
            text = normalize(box.text)
            if text:
                cur_paras.append(Paragraph(text, _coords(page, box, sizes)))
        elif box.type in LAYOUT_FIGURE:
            order += 1
            kind = "table" if box.type in _TABLE_TYPES else "figure"
            caption = normalize(box.text)
            figures.append(
                Figure(kind, _figure_label(caption, order, kind), caption, _coords(page, box, sizes))
            )
    flush()
    return sections, figures, order
```

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/test_layout.py -v`
Expected: PASS.

> Note on figure captions: PaddleOCR emits the caption as a separate `text` block, so an `image` layout's own `text` is often empty and the caption becomes a paragraph in the current section. Pinning caption-to-figure association is refined in Task 7 (pipeline) after seeing the real fixture; for now the label falls back to `Figure {n}` and the nearby caption still appears in the section text. This is acceptable — the server tolerates generic labels.

- [ ] **Step 7: Commit**

```bash
git add src/scholarflow_ocr/parse/document.py src/scholarflow_ocr/parse/text.py src/scholarflow_ocr/parse/layout.py tests/test_layout.py
git commit -m "feat: add document model and layout-to-body mapping"
```

---

## Task 5: Front-matter extraction (title, abstract, authors, doi, year)

**Files:**
- Create: `src/scholarflow_ocr/parse/frontmatter.py`
- Test: `tests/test_frontmatter.py`

**Interfaces:**
- Produces: `extract_frontmatter(first_page:Page) -> FrontMatter` where `FrontMatter` is a frozen dataclass `(title:str, abstract:str, authors:tuple[Author,...], doi:str, year:str)`.
- Consumes: `Page`/`LayoutBox` (Task 2), `Author` (Task 4), `split_name`/`normalize` (Task 4).

- [ ] **Step 1: Write the failing test** `tests/test_frontmatter.py`

```python
from scholarflow_ocr.ocr.models import LayoutBox, Page
from scholarflow_ocr.parse.document import Author
from scholarflow_ocr.parse.frontmatter import extract_frontmatter


def test_extract_frontmatter():
    page = Page(
        page_num=1, width_px=1000, height_px=1400,
        layouts=(
            LayoutBox(1, "title", "A Great Paper", (0, 10, 400, 30)),
            LayoutBox(2, "text", "Jane Q Public, John Doe", (0, 50, 400, 20)),
            LayoutBox(3, "title", "Abstract", (0, 90, 200, 20)),
            LayoutBox(4, "text", "We present something. doi:10.1145/1234567 (2024)", (0, 120, 400, 60)),
        ),
    )
    fm = extract_frontmatter(page)
    assert fm.title == "A Great Paper"
    assert fm.abstract.startswith("We present something.")
    assert fm.authors == (Author("Jane Q", "Public"), Author("John", "Doe"))
    assert fm.doi == "10.1145/1234567"
    assert fm.year == "2024"


def test_extract_frontmatter_author_forename():
    page = Page(1, 1000, 1400, (
        LayoutBox(1, "title", "T", (0, 0, 10, 10)),
        LayoutBox(2, "text", "John Doe", (0, 20, 10, 10)),
        LayoutBox(3, "title", "Abstract", (0, 40, 10, 10)),
        LayoutBox(4, "text", "Body.", (0, 60, 10, 10)),
    ))
    fm = extract_frontmatter(page)
    assert fm.authors == (Author("John", "Doe"),)
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/scholarflow_ocr/parse/frontmatter.py`**

```python
import re
from dataclasses import dataclass

from scholarflow_ocr.ocr.models import Page
from scholarflow_ocr.parse.document import Author
from scholarflow_ocr.parse.layout import LAYOUT_TEXT, LAYOUT_TITLE
from scholarflow_ocr.parse.text import normalize, split_name

_DOI = re.compile(r"10\.\d{4,9}/[^\s,;]+")
_YEAR = re.compile(r"(?:19|20)\d{2}")
_ABSTRACT = re.compile(r"^abstract\b", re.IGNORECASE)


@dataclass(frozen=True)
class FrontMatter:
    title: str
    abstract: str
    authors: tuple[Author, ...]
    doi: str
    year: str


def _authors_from(text: str) -> tuple[Author, ...]:
    names = [normalize(part) for part in re.split(r"[,;]| and ", text) if normalize(part)]
    authors: list[Author] = []
    for name in names:
        fore, sur = split_name(name)
        if sur:
            authors.append(Author(fore, sur))
    return tuple(authors)


def extract_frontmatter(first_page: Page) -> FrontMatter:
    title = ""
    abstract_parts: list[str] = []
    author_text = ""
    in_abstract = False
    seen_title = False

    for box in first_page.layouts:
        text = normalize(box.text)
        if box.type in LAYOUT_TITLE:
            if _ABSTRACT.match(text):
                in_abstract = True
                continue
            in_abstract = False
            if not seen_title and text:
                title = text
                seen_title = True
            continue
        if box.type in LAYOUT_TEXT:
            if in_abstract:
                abstract_parts.append(text)
            elif seen_title and not author_text and not abstract_parts:
                author_text = text
    abstract = " ".join(p for p in abstract_parts if p).strip()
    haystack = f"{author_text} {abstract}"
    doi_m = _DOI.search(haystack)
    year_m = _YEAR.search(haystack)
    return FrontMatter(
        title=title,
        abstract=abstract,
        authors=_authors_from(author_text),
        doi=doi_m.group(0) if doi_m else "",
        year=year_m.group(0) if year_m else "",
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_frontmatter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scholarflow_ocr/parse/frontmatter.py tests/test_frontmatter.py
git commit -m "feat: add front-matter extraction"
```

---

## Task 6: Heuristic reference parsing

**Files:**
- Create: `src/scholarflow_ocr/parse/references.py`
- Test: `tests/test_references.py`

**Interfaces:**
- Produces:
  - `is_references_heading(text:str) -> bool`
  - `split_entries(block:str) -> list[str]` (split a bibliography blob into entry strings)
  - `parse_entry(order:int, raw:str) -> Reference`
  - `parse_references(entries:list[str]) -> list[Reference]`
- Consumes: `Reference` (Task 4), `normalize`/`split_name` (Task 4).

- [ ] **Step 1: Write the failing test** `tests/test_references.py`

```python
from scholarflow_ocr.parse.references import (
    is_references_heading, parse_entry, parse_references, split_entries,
)


def test_is_references_heading():
    assert is_references_heading("References")
    assert is_references_heading("REFERENCES")
    assert is_references_heading("Bibliography")
    assert not is_references_heading("Reference implementation")


def test_split_entries_numbered():
    block = "[1] A. Smith. Title one. Venue, 2020.\n[2] B. Jones. Title two. J. Foo, 2021."
    entries = split_entries(block)
    assert len(entries) == 2
    assert entries[0].startswith("A. Smith")


def test_parse_entry_extracts_fields():
    ref = parse_entry(1, "A. Smith and B. Jones. A great title. Journal of Foo, 2020. doi:10.1/xyz")
    assert ref.order == 1
    assert ref.year == "2020"
    assert ref.doi == "10.1/xyz"
    assert "A great title" in ref.title
    assert ref.raw_text.startswith("A. Smith")
    assert any("Smith" in a for a in ref.authors)


def test_parse_references_roundtrip():
    refs = parse_references(["X. Y. Title. Venue, 1999."])
    assert refs[0].order == 1
    assert refs[0].year == "1999"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_references.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/scholarflow_ocr/parse/references.py`**

```python
import re

from scholarflow_ocr.parse.document import Reference
from scholarflow_ocr.parse.text import normalize

_HEADING = re.compile(r"^\s*(references|bibliography)\s*$", re.IGNORECASE)
_MARKER = re.compile(r"(?:^|\n)\s*\[\d+\]\s*|(?:^|\n)\s*\d+\.\s+")
_DOI = re.compile(r"10\.\d{4,9}/[^\s,;]+")
_YEAR = re.compile(r"(?:19|20)\d{2}")
# Leading author run: sequences like "A. Smith, B. Jones." up to the first "."
# that is followed by a capitalized title word. Heuristic and best-effort.
_AUTHORS = re.compile(r"^(?P<authors>(?:[A-Z]\.\s*)*[A-Z][a-z]+(?:\s+and\s+|,\s*|\.\s*))+")


def is_references_heading(text: str) -> bool:
    return bool(_HEADING.match(normalize(text)))


def split_entries(block: str) -> list[str]:
    if not block.strip():
        return []
    if _MARKER.search(block):
        parts = _MARKER.split(block)
        return [normalize(p) for p in parts if normalize(p)]
    # Fallback: one entry per non-empty line.
    return [normalize(line) for line in block.splitlines() if normalize(line)]


def parse_entry(order: int, raw: str) -> Reference:
    raw_norm = normalize(raw)
    doi_m = _DOI.search(raw_norm)
    year_m = _YEAR.search(raw_norm)
    doi = doi_m.group(0) if doi_m else ""
    year = year_m.group(0) if year_m else ""

    authors: tuple[str, ...] = ()
    remainder = raw_norm
    am = _AUTHORS.match(raw_norm)
    if am:
        author_str = am.group("authors")
        remainder = raw_norm[am.end():]
        authors = tuple(
            normalize(a) for a in re.split(r",|\band\b", author_str) if normalize(a).rstrip(".")
        )

    # Title = text up to the year or the first sentence break after authors.
    title = remainder
    if year and year in remainder:
        title = remainder.split(year, 1)[0]
    title = normalize(title.strip(" .,"))

    return Reference(order=order, title=title, authors=authors, venue="", year=year, doi=doi, raw_text=raw_norm)


def parse_references(entries: list[str]) -> list[Reference]:
    return [parse_entry(i + 1, e) for i, e in enumerate(entries) if normalize(e)]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_references.py -v`
Expected: PASS. If `test_parse_entry_extracts_fields` fails on the author regex, adjust `_AUTHORS`/assertions together — the guarantee that matters is `raw_text` is always preserved; field extraction is best-effort.

- [ ] **Step 5: Commit**

```bash
git add src/scholarflow_ocr/parse/references.py tests/test_references.py
git commit -m "feat: add heuristic reference parser"
```

---

## Task 7: Pipeline — ParseResult + page sizes → Document

**Files:**
- Create: `src/scholarflow_ocr/parse/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `build_document(result:ParseResult, sizes:list[tuple[float,float]]) -> Document`.
- Consumes: everything from Tasks 4–6 plus `ParseResult`/`Page` (Task 2).

Logic: page 1 → front-matter (title/abstract/authors/doi/year). Across all pages, accumulate body sections + figures via `build_body`. When a section heading is a references heading, stop treating following blocks as body and route their text into the reference collector instead; parse it at the end.

- [ ] **Step 1: Write the failing test** `tests/test_pipeline.py`

```python
from scholarflow_ocr.ocr.models import LayoutBox, Page, ParseResult
from scholarflow_ocr.parse.pipeline import build_document


def test_build_document_end_to_end():
    page1 = Page(1, 1000, 1400, (
        LayoutBox(1, "title", "Cool Paper", (0, 0, 400, 30)),
        LayoutBox(2, "text", "Ada Lovelace, Alan Turing", (0, 40, 400, 20)),
        LayoutBox(3, "title", "Abstract", (0, 80, 200, 20)),
        LayoutBox(4, "text", "A study. (2023)", (0, 110, 400, 40)),
        LayoutBox(5, "title", "1 Introduction", (0, 160, 300, 20)),
        LayoutBox(6, "text", "Intro text.", (0, 190, 400, 40)),
    ))
    page2 = Page(2, 1000, 1400, (
        LayoutBox(1, "title", "References", (0, 0, 200, 20)),
        LayoutBox(2, "text", "[1] A. Smith. A title. Venue, 2020.", (0, 30, 400, 20)),
    ))
    doc = build_document(ParseResult((page1, page2)), sizes=[(500.0, 700.0), (500.0, 700.0)])
    assert doc.title == "Cool Paper"
    assert doc.abstract.startswith("A study")
    assert len(doc.authors) == 2
    assert any(s.heading == "Introduction" and s.number == "1" for s in doc.sections)
    # references heading is NOT a body section
    assert all(s.heading != "References" for s in doc.sections)
    assert len(doc.references) == 1
    assert doc.references[0].year == "2020"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/scholarflow_ocr/parse/pipeline.py`**

```python
from scholarflow_ocr.ocr.models import ParseResult
from scholarflow_ocr.parse.document import Document
from scholarflow_ocr.parse.frontmatter import extract_frontmatter
from scholarflow_ocr.parse.layout import (
    LAYOUT_TEXT, LAYOUT_TITLE, build_body,
)
from scholarflow_ocr.parse.references import (
    is_references_heading, parse_references, split_entries,
)
from scholarflow_ocr.parse.text import normalize


def build_document(result: ParseResult, sizes: list[tuple[float, float]]) -> Document:
    fm = None
    sections = []
    figures = []
    order = 0
    ref_texts: list[str] = []
    in_refs = False

    for i, page in enumerate(result.pages):
        if i == 0:
            fm = extract_frontmatter(page)

        # Collect references once we cross the References heading (any page).
        kept_layouts = []
        for box in page.layouts:
            if box.type in LAYOUT_TITLE and is_references_heading(box.text):
                in_refs = True
                continue
            if in_refs:
                if box.type in LAYOUT_TEXT and normalize(box.text):
                    ref_texts.append(normalize(box.text))
                continue
            kept_layouts.append(box)

        if kept_layouts:
            trimmed = page.__class__(page.page_num, page.width_px, page.height_px, tuple(kept_layouts))
            page_sections, page_figures, order = build_body(trimmed, sizes, order)
            sections.extend(page_sections)
            figures.extend(page_figures)

    references = parse_references(split_entries("\n".join(ref_texts)))

    fm = fm or extract_frontmatter(result.pages[0]) if result.pages else None
    return Document(
        title=fm.title if fm else "",
        abstract=fm.abstract if fm else "",
        doi=fm.doi if fm else "",
        year=fm.year if fm else "",
        authors=fm.authors if fm else (),
        sections=tuple(sections),
        figures=tuple(figures),
        references=tuple(references),
    )
```

> Note: page-1 front-matter blocks (title, author line, abstract) are also seen by `build_body` and would become a stray leading section. That is harmless for the server, but to keep the body clean the pipeline relies on front-matter living above the first numbered heading; refine trimming here once the real fixture shows the exact page-1 shape.

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scholarflow_ocr/parse/pipeline.py tests/test_pipeline.py
git commit -m "feat: assemble Document from OCR result"
```

---

## Task 8: TEI renderer + server-contract test

**Files:**
- Create: `src/scholarflow_ocr/tei/__init__.py`, `src/scholarflow_ocr/tei/render.py`
- Test: `tests/test_tei_render.py`, `tests/test_contract.py`

**Interfaces:**
- Produces: `render_tei(doc:Document) -> str` (TEI XML string, no namespace).
- Consumes: `Document` and its members (Task 4), `split_name` (Task 4).

- [ ] **Step 1: Write the failing test** `tests/test_tei_render.py`

```python
from lxml import etree

from scholarflow_ocr.parse.coords import Coords
from scholarflow_ocr.parse.document import (
    Author, Document, Figure, Paragraph, Reference, Section,
)
from scholarflow_ocr.tei.render import render_tei


def _doc() -> Document:
    return Document(
        title="A Title",
        abstract="An abstract.",
        doi="10.1/xyz",
        year="2024",
        authors=(Author("Jane", "Public"),),
        sections=(
            Section("2.1", "Method", (Paragraph("Body.", Coords(1, 1, 2, 3, 4)),), Coords(1, 5, 6, 7, 8)),
        ),
        figures=(Figure("figure", "Figure 1", "A caption.", Coords(2, 1, 2, 3, 4)),),
        references=(Reference(1, "Ref title", ("A. Smith",), "A Venue", "2020", "10.2/abc", "raw"),),
    )


def test_render_tei_paths():
    xml = render_tei(_doc())
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext("teiHeader/fileDesc/titleStmt/title") == "A Title"
    assert root.findtext("teiHeader/profileDesc/abstract/p") == "An abstract."
    head = root.find("text/body/div/head")
    assert head.get("n") == "2.1"
    assert head.get("coords") == "1,5.00,6.00,7.00,8.00"
    assert head.text == "Method"
    assert root.find("text/body/div/p").get("coords") == "1,1.00,2.00,3.00,4.00"
    fig = root.find("text/body/figure")
    assert fig.findtext("head") == "Figure 1"
    assert fig.findtext("figDesc") == "A caption."
    idno = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/idno")
    assert idno.get("type") == "DOI" and idno.text == "10.1/xyz"
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_tei_render.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `src/scholarflow_ocr/tei/__init__.py`** (empty) and `src/scholarflow_ocr/tei/render.py`

```python
from lxml import etree

from scholarflow_ocr.parse.document import Document
from scholarflow_ocr.parse.text import split_name


def _persname(parent, forename: str, surname: str) -> None:
    author = etree.SubElement(parent, "author")
    pers = etree.SubElement(author, "persName")
    if forename:
        etree.SubElement(pers, "forename").text = forename
    if surname:
        etree.SubElement(pers, "surname").text = surname


def render_tei(doc: Document) -> str:
    tei = etree.Element("TEI")

    header = etree.SubElement(tei, "teiHeader")
    file_desc = etree.SubElement(header, "fileDesc")
    title_stmt = etree.SubElement(file_desc, "titleStmt")
    etree.SubElement(title_stmt, "title").text = doc.title

    source_desc = etree.SubElement(file_desc, "sourceDesc")
    bibl = etree.SubElement(source_desc, "biblStruct")
    analytic = etree.SubElement(bibl, "analytic")
    for a in doc.authors:
        _persname(analytic, a.forename, a.surname)
    monogr = etree.SubElement(bibl, "monogr")
    imprint = etree.SubElement(monogr, "imprint")
    if doc.year:
        etree.SubElement(imprint, "date").set("when", doc.year)
    if doc.doi:
        idno = etree.SubElement(bibl, "idno")
        idno.set("type", "DOI")
        idno.text = doc.doi

    profile = etree.SubElement(header, "profileDesc")
    abstract = etree.SubElement(profile, "abstract")
    if doc.abstract:
        etree.SubElement(abstract, "p").text = doc.abstract

    text = etree.SubElement(tei, "text")
    body = etree.SubElement(text, "body")
    for s in doc.sections:
        div = etree.SubElement(body, "div")
        head = etree.SubElement(div, "head")
        if s.number:
            head.set("n", s.number)
        if s.coords:
            head.set("coords", s.coords.tei())
        head.text = s.heading
        for para in s.paragraphs:
            p = etree.SubElement(div, "p")
            if para.coords:
                p.set("coords", para.coords.tei())
            p.text = para.text
    for f in doc.figures:
        fig = etree.SubElement(body, "figure")
        if f.kind == "table":
            fig.set("type", "table")
        if f.coords:
            fig.set("coords", f.coords.tei())
        etree.SubElement(fig, "head").text = f.label
        etree.SubElement(fig, "figDesc").text = f.caption

    back = etree.SubElement(text, "back")
    back_div = etree.SubElement(back, "div")
    list_bibl = etree.SubElement(back_div, "listBibl")
    for r in doc.references:
        bs = etree.SubElement(list_bibl, "biblStruct")
        r_analytic = etree.SubElement(bs, "analytic")
        if r.title:
            etree.SubElement(r_analytic, "title").text = r.title
        for name in r.authors:
            fore, sur = split_name(name)
            _persname(r_analytic, fore, sur)
        r_monogr = etree.SubElement(bs, "monogr")
        if r.venue:
            etree.SubElement(r_monogr, "title").text = r.venue
        r_imprint = etree.SubElement(r_monogr, "imprint")
        if r.year:
            etree.SubElement(r_imprint, "date").set("when", r.year)
        if r.doi:
            idn = etree.SubElement(bs, "idno")
            idn.set("type", "DOI")
            idn.text = r.doi

    return etree.tostring(tei, pretty_print=True, encoding="unicode")
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_tei_render.py -v`
Expected: PASS.

- [ ] **Step 5: Write the contract test** `tests/test_contract.py` — mirrors what `scholarflow-server/internal/parser/grobid.go` extracts, asserting our TEI is readable by the server's logic.

```python
from lxml import etree

from scholarflow_ocr.parse.coords import Coords
from scholarflow_ocr.parse.document import (
    Author, Document, Figure, Paragraph, Reference, Section,
)
from scholarflow_ocr.tei.render import render_tei


def _first_page_of_coords(coords: str) -> int:
    # Reproduces grobid.go parsePage: first integer of "page,x,y,w,h".
    return int(coords.split(",")[0])


def test_server_would_extract_all_fields():
    doc = Document(
        title="Contract Paper",
        abstract="Abstract body.",
        doi="10.1/aaa",
        year="2022",
        authors=(Author("Grace", "Hopper"),),
        sections=(Section("1", "Intro", (Paragraph("Text.", Coords(3, 1, 1, 1, 1)),), Coords(3, 1, 1, 1, 1)),),
        figures=(Figure("table", "Table 1", "Cap.", Coords(4, 1, 1, 1, 1)),),
        references=(Reference(1, "R Title", ("I. Newton",), "Nature", "1687", "10.9/zzz", "raw"),),
    )
    root = etree.fromstring(render_tei(doc).encode("utf-8"))

    # Header (grobid.go: title, abstract, analytic authors, DOI, year)
    assert root.findtext("teiHeader/fileDesc/titleStmt/title") == "Contract Paper"
    assert root.findtext("teiHeader/profileDesc/abstract/p") == "Abstract body."
    pers = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/analytic/author/persName")
    assert pers.findtext("forename") == "Grace"
    assert pers.findtext("surname") == "Hopper"
    idno = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/idno")
    assert idno.get("type") == "DOI" and idno.text == "10.1/aaa"
    when = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/monogr/imprint/date").get("when")
    assert when.startswith("2022")

    # Body div/head@n + coords page, p, figure
    div = root.find("text/body/div")
    assert div.find("head").get("n") == "1"
    assert _first_page_of_coords(div.find("head").get("coords")) == 3
    assert div.findtext("p") == "Text."
    fig = root.find("text/body/figure")
    assert fig.get("type") == "table"
    assert fig.findtext("head") == "Table 1"
    assert fig.findtext("figDesc") == "Cap."
    assert _first_page_of_coords(fig.get("coords")) == 4

    # References under text/back/div/listBibl/biblStruct
    bibl = root.find("text/back/div/listBibl/biblStruct")
    assert bibl.findtext("analytic/title") == "R Title"
    assert bibl.find("analytic/author/persName/surname").text == "Newton"
    assert bibl.findtext("monogr/title") == "Nature"
    assert bibl.find("monogr/imprint/date").get("when") == "1687"
    assert bibl.find("idno").get("type") == "DOI"
```

- [ ] **Step 6: Run the contract test, verify pass**

Run: `python -m pytest tests/test_contract.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/scholarflow_ocr/tei tests/test_tei_render.py tests/test_contract.py
git commit -m "feat: render TEI and verify server-contract compatibility"
```

---

## Task 9: HTTP endpoint wiring (GROBID-compatible)

**Files:**
- Modify: `src/scholarflow_ocr/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `create_app(ocr_client=None, sizes_fn=None)` — when `ocr_client` is provided it is used directly (tests inject `FakeOCRClient`); otherwise a `BaiduOCRClient` is built from `load_config()`. Route `POST /api/processFulltextDocument` accepts multipart field `input`, returns `200 application/xml` (TEI) or `400`/`5xx`.
- Consumes: `page_point_sizes` (Task 3), `build_document` (Task 7), `render_tei` (Task 8), `BaiduOCRClient`/`OCRError` (Task 2).

- [ ] **Step 1: Write the failing test** `tests/test_api.py`

```python
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
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL (`create_app()` takes no args / route missing).

- [ ] **Step 3: Replace `src/scholarflow_ocr/api.py`**

```python
import logging

from fastapi import FastAPI, Request, Response

from scholarflow_ocr.config import load_config
from scholarflow_ocr.ocr.client import BaiduOCRClient, OCRError
from scholarflow_ocr.parse.pipeline import build_document
from scholarflow_ocr.pdfmeta import page_point_sizes
from scholarflow_ocr.tei.render import render_tei

log = logging.getLogger("scholarflow_ocr")


def create_app(ocr_client=None, sizes_fn=None) -> FastAPI:
    app = FastAPI(title="scholarflow-ocr")
    _client = ocr_client
    _sizes = sizes_fn or page_point_sizes

    def client():
        nonlocal _client
        if _client is None:
            _client = BaiduOCRClient(load_config())
        return _client

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/isalive")
    def isalive() -> Response:
        return Response(content="true", media_type="text/plain")

    @app.post("/api/processFulltextDocument")
    async def process_fulltext(request: Request) -> Response:
        form = await request.form()
        upload = form.get("input")
        if upload is None or not hasattr(upload, "read"):
            return Response(content="missing 'input' file field", status_code=400)
        pdf = await upload.read()
        if not pdf:
            return Response(content="empty upload", status_code=400)
        try:
            sizes = _sizes(pdf)
        except Exception as exc:  # malformed PDF
            log.warning("pdf sizing failed: %s", exc)
            return Response(content="invalid pdf", status_code=400)
        try:
            result = client().parse(pdf, getattr(upload, "filename", "upload.pdf"))
        except OCRError as exc:
            log.error("ocr failed: %s", exc)
            return Response(content="ocr backend error", status_code=502)
        doc = build_document(result, sizes)
        tei = render_tei(doc)
        return Response(content=tei, media_type="application/xml")

    return app
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS (three tests).

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add src/scholarflow_ocr/api.py tests/test_api.py
git commit -m "feat: add GROBID-compatible processFulltextDocument endpoint"
```

---

## Task 10: Docker, compose, runbook, and server integration note

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`
- Modify: `README.md`
- Create: `docs/server-integration.md`

**Interfaces:** none (packaging/docs).

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV HTTP_PORT=8070
EXPOSE 8070
CMD ["python", "-m", "scholarflow_ocr.main"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  ocr:
    build: .
    ports:
      - "${HTTP_PORT:-8070}:8070"
    environment:
      BAIDU_OCR_APP_ID: ${BAIDU_OCR_APP_ID}
      BAIDU_OCR_API_KEY: ${BAIDU_OCR_API_KEY}
      BAIDU_OCR_SECRET_KEY: ${BAIDU_OCR_SECRET_KEY}
      BAIDU_OCR_ENDPOINT: ${BAIDU_OCR_ENDPOINT:-https://aip.baidubce.com}
      HTTP_PORT: 8070
      OCR_POLL_TIMEOUT_SECONDS: ${OCR_POLL_TIMEOUT_SECONDS:-300}
      OCR_POLL_INTERVAL_SECONDS: ${OCR_POLL_INTERVAL_SECONDS:-3}
      MAX_UPLOAD_BYTES: ${MAX_UPLOAD_BYTES:-33554432}
    restart: unless-stopped
```

- [ ] **Step 3: Build the image and verify size/boot**

Run:
```bash
docker build -t scholarflow-ocr .
docker images scholarflow-ocr --format '{{.Size}}'
```
Expected: image builds; size < 200 MB.

- [ ] **Step 4: Smoke-test the container health endpoint**

Run:
```bash
docker run -d --name ocr-smoke -e BAIDU_OCR_API_KEY=x -e BAIDU_OCR_SECRET_KEY=y -p 8070:8070 scholarflow-ocr
sleep 2 && curl -fsS http://localhost:8070/health && echo
docker rm -f ocr-smoke
```
Expected: `{"status":"ok"}`.

- [ ] **Step 5: Write `docs/server-integration.md`** (documents the single server-side change)

```markdown
# Integrating scholarflow-ocr with scholarflow-server

scholarflow-ocr impersonates GROBID's `POST /api/processFulltextDocument`, so the
server integrates by pointing `GROBID_URL` at this service:

    GROBID_URL=http://<ocr-host>:8070

## Required server change: configurable GROBID timeout

`scholarflow-server/internal/parser/grobid.go` hardcodes a 2-minute client
timeout:

    client: &http.Client{Timeout: 2 * time.Minute}

PaddleOCR-VL async parsing of a large PDF can exceed this. Change it to read a
config value (default preserved), e.g. add `GROBIDTimeoutSeconds` to
`internal/config/config.go` (env `GROBID_TIMEOUT_SECONDS`, default `120`) and use
it in `NewGROBIDParser`. Raise it (e.g. 600) for this deployment.

This is the only server code change required.
```

- [ ] **Step 6: Update `README.md`** — replace the "Design in progress" line with a runbook

```markdown
## Run

    cp .env.example .env      # fill in Baidu credentials
    docker compose up --build

Point the server at it: set `GROBID_URL=http://<host>:8070` in scholarflow-server.
See `docs/server-integration.md` for the one required server change.

## Develop

    python -m pip install -e '.[dev]'
    python -m pytest -v
```

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml docs/server-integration.md README.md
git commit -m "chore: add docker packaging and server integration docs"
```

---

## Final verification

- [ ] Run the full suite: `python -m pytest -v` → all pass.
- [ ] Confirm no secrets are tracked: `git ls-files | grep -E '\.env$'` → empty.
- [ ] Replace the hand-written fixture (if used) with a real capture and re-run
      layout/pipeline tests against real `type` values.
- [ ] Manual end-to-end (needs real creds): `docker compose up`, then
      `curl -F input=@sample.pdf http://localhost:8070/api/processFulltextDocument`
      and eyeball the TEI.

## Notes for the executor

- The two structuring modules with real-world risk are `parse/layout.py`
  (depends on PaddleOCR's exact `type` strings) and `parse/references.py`
  (heuristic). Both are isolated behind tests; adjust their constants/regexes
  against the captured fixture without touching the TEI contract or the server.
- Never commit `.env`. Rotate the Baidu keys after development (they were shared
  in plaintext).
```
