import json
from pathlib import Path

from scholarflow_ocr.ocr.models import parse_result_from_json
from scholarflow_ocr.parse.pipeline import build_document

FIXTURE = Path(__file__).parent / "fixtures" / "real_slice_parse_result.json"


def _load_document():
    data = json.loads(FIXTURE.read_text())
    result = parse_result_from_json(data)
    sizes = [(p["meta"]["page_width"], p["meta"]["page_height"]) for p in data["pages"]]
    return build_document(result, sizes)


def test_real_fixture_title_and_abstract():
    doc = _load_document()
    assert "Temporal Difference Learning" in doc.title
    assert doc.abstract
    assert "model predictive control" in doc.abstract.lower()


def test_real_fixture_authors():
    doc = _load_document()
    assert len(doc.authors) == 3
    assert [a.surname for a in doc.authors] == ["Hansen", "Wang", "Su"]


def test_real_fixture_sections():
    doc = _load_document()
    assert len(doc.sections) >= 3
    numbers = {s.number for s in doc.sections}
    assert {"1", "2", "3"} <= numbers

    by_number = {s.number: s.heading for s in doc.sections}
    assert "Introduction" in by_number["1"]
    assert "Preliminaries" in by_number["2"]
    assert "TD-Learning" in by_number["3"]

    # Front-matter (title / "Abstract" heading) must not leak into sections.
    assert all(s.heading != doc.title for s in doc.sections)
    assert all(s.heading != "Abstract" for s in doc.sections)


def test_real_fixture_figures():
    doc = _load_document()
    assert len(doc.figures) >= 2
    assert any("Figure 1" in f.caption for f in doc.figures)
