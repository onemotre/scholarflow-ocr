from scholarflow_ocr.ocr.models import ParseResult


class FakeOCRClient:
    def __init__(self, result: ParseResult) -> None:
        self._result = result

    def parse(self, pdf: bytes, file_name: str) -> ParseResult:
        return self._result
