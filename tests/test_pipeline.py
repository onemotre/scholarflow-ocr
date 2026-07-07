from scholarflow_ocr.ocr.models import LayoutBox, Page, ParseResult
from scholarflow_ocr.parse.pipeline import build_document


def test_build_document_end_to_end():
    page1 = Page(1, 1000, 1400, (
        LayoutBox(1, "title", "Cool Paper", (0, 0, 400, 30)),
        LayoutBox(2, "text", "Ada Lovelace, Alan Turing", (0, 40, 400, 20)),
        LayoutBox(3, "title", "Abstract", (0, 80, 200, 20)),
        LayoutBox(4, "text", "A study. (2023)", (0, 110, 400, 40)),
        LayoutBox(5, "title", "1 Introduction", (0, 160, 300, 20)),
        LayoutBox(6, "text", "Intro text.", (0, 190, 400, 40)),
    ))
    page2 = Page(2, 1000, 1400, (
        LayoutBox(1, "title", "References", (0, 0, 200, 20)),
        LayoutBox(2, "text", "[1] A. Smith. A title. Venue, 2020.", (0, 30, 400, 20)),
    ))
    doc = build_document(ParseResult((page1, page2)), sizes=[(500.0, 700.0), (500.0, 700.0)])
    assert doc.title == "Cool Paper"
    assert doc.abstract.startswith("A study")
    assert len(doc.authors) == 2
    assert any(s.heading == "Introduction" and s.number == "1" for s in doc.sections)
    # references heading is NOT a body section
    assert all(s.heading != "References" for s in doc.sections)
    # page-1 front-matter (title/authors/Abstract) is excluded from the body
    # sections now that it's dropped up to the first numbered heading.
    assert all(s.heading not in ("Cool Paper", "Abstract") for s in doc.sections)
    assert len(doc.references) == 1
    assert doc.references[0].year == "2020"
