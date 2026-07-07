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
