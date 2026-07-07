import re
from dataclasses import dataclass

from scholarflow_ocr.ocr.models import Page
from scholarflow_ocr.parse.document import Author
from scholarflow_ocr.parse.layout import LAYOUT_TEXT, LAYOUT_TITLE
from scholarflow_ocr.parse.text import normalize, split_name

_DOI = re.compile(r"10\.\d{4,9}/[^\s,;]+")
_YEAR = re.compile(r"(?:19|20)\d{2}")
_ABSTRACT = re.compile(r"^abstract\b", re.IGNORECASE)

# Real PaddleOCR-VL author lines carry LaTeX affiliation markers, e.g.
# "Nicklas Hansen $ ^{1} $ Xiaolong Wang $ ^{*1} $ Hao Su $ ^{*1} $".
_LATEX_MATH_SPAN = re.compile(r"\$[^$]*\$")
_LATEX_SUPERSCRIPT = re.compile(r"\^\{[^}]*\}|\^\S+")
_AUTHOR_SPLIT = re.compile(r"\s{2,}|[,;]|\s+and\s+")


@dataclass(frozen=True)
class FrontMatter:
    title: str
    abstract: str
    authors: tuple[Author, ...]
    doi: str
    year: str


def _strip_latex_affiliation_markers(text: str) -> str:
    """Remove LaTeX math spans and leftover superscript markers from an author line."""
    text = _LATEX_MATH_SPAN.sub(" ", text)
    text = _LATEX_SUPERSCRIPT.sub(" ", text)
    return text


def _split_author_names(text: str) -> list[str]:
    cleaned = _strip_latex_affiliation_markers(text)
    return [normalize(part) for part in _AUTHOR_SPLIT.split(cleaned) if normalize(part)]


def _authors_from(text: str) -> tuple[Author, ...]:
    authors: list[Author] = []
    for name in _split_author_names(text):
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
        if box.type == "abstract":
            # Real PaddleOCR-VL emits the abstract BODY as its own dedicated
            # type, independent of the "Abstract" heading. Always capture it.
            if text:
                abstract_parts.append(text)
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
