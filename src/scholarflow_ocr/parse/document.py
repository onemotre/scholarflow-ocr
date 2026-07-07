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
