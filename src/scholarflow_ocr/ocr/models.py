from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LayoutBox:
    # PaddleOCR-VL returns layout_id as an opaque string (e.g. "1Y3HgC-layout-1"),
    # so keep it as-is rather than coercing to int.
    layout_id: str
    type: str
    text: str
    position: tuple[float, float, float, float]  # x, y, w, h (page coord space)
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
    # PaddleOCR-VL numbers pages from 0 (observed: page_num 0,1,2,...). The rest of
    # the system, and GROBID-style TEI @coords, require 1-based page numbers (the
    # server rejects page <= 0). Rather than trust the API's base, derive a 1-based
    # page number from array position; `sizes` passed downstream are aligned to the
    # same order, so index i ↔ page (i+1).
    for i, p in enumerate(data.get("pages", []) or []):
        meta = p.get("meta", {}) or {}
        layouts = tuple(
            LayoutBox(
                layout_id=str(lay.get("layout_id", "") or ""),
                type=str(lay.get("type", "") or ""),
                text=str(lay.get("text", "") or ""),
                position=_position(lay.get("position")),
                sub_type=str(lay.get("sub_type", "") or ""),
            )
            for lay in (p.get("layouts", []) or [])
        )
        pages.append(
            Page(
                page_num=i + 1,
                width_px=float(meta.get("page_width", 0) or 0),
                height_px=float(meta.get("page_height", 0) or 0),
                layouts=layouts,
            )
        )
    return ParseResult(pages=tuple(pages))
