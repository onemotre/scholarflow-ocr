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
