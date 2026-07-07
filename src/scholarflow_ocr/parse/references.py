import re

from scholarflow_ocr.parse.document import Reference
from scholarflow_ocr.parse.text import normalize

_HEADING = re.compile(r"^\s*(references|bibliography)\s*$", re.IGNORECASE)
_MARKER = re.compile(r"(?:^|\n)\s*\[\d+\]\s*|(?:^|\n)\s*\d+\.\s+")
_DOI = re.compile(r"10\.\d{4,9}/[^\s,;]+")
_YEAR = re.compile(r"(?:19|20)\d{2}")
# Matches a leading run of and/comma-separated author names, best-effort.
_AUTHORS = re.compile(r"^(?P<authors>(?:[A-Z]\.?\s*)*[A-Z][a-z]+(?:(?:\s+and\s+|,\s+)(?:[A-Z]\.?\s*)*[A-Z][a-z]+)*(?:\.\s*)?)")


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
