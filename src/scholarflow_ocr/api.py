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
        # Untrusted input boundary: any failure to parse the uploaded bytes as a PDF is treated as a 400 bad upload (pypdf raises varied exception types on malformed input).
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
