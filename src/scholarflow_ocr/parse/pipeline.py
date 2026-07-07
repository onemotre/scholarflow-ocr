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
