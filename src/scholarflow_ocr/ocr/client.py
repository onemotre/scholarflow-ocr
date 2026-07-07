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

    def _request_json(self, method: str, url: str, **kwargs) -> dict:
        try:
            resp = self._http.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise OCRError(f"HTTP call failed ({method} {url}): {exc}") from exc

    def _access_token(self) -> str:
        body = self._request_json(
            "POST",
            f"{self._base()}/oauth/2.0/token",
            params={
                "grant_type": "client_credentials",
                "client_id": self._cfg.api_key,
                "client_secret": self._cfg.secret_key,
            },
        )
        token = body.get("access_token")
        if not token:
            raise OCRError("no access_token in oauth response")
        return token

    def _submit(self, token: str, pdf: bytes, file_name: str) -> str:
        body = self._request_json(
            "POST",
            f"{self._base()}/rest/2.0/brain/online/v2/paddle-vl-parser/task",
            params={"access_token": token},
            data={"file_data": base64.b64encode(pdf).decode("ascii"), "file_name": file_name},
        )
        if body.get("error_code"):
            raise OCRError(f"submit failed: {body.get('error_code')} {body.get('error_msg')}")
        task_id = (body.get("result") or {}).get("task_id")
        if not task_id:
            raise OCRError("submit returned no task_id")
        return task_id

    def _poll(self, token: str, task_id: str) -> str:
        deadline = time.monotonic() + self._cfg.poll_timeout_seconds
        while True:
            body = self._request_json(
                "POST",
                f"{self._base()}/rest/2.0/brain/online/v2/paddle-vl-parser/task/query",
                params={"access_token": token},
                data={"task_id": task_id},
            )
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
        return self._request_json("GET", url)
