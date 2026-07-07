from scholarflow_ocr.parse.references import (
    is_references_heading, parse_entry, parse_references, split_entries,
)


def test_is_references_heading():
    assert is_references_heading("References")
    assert is_references_heading("REFERENCES")
    assert is_references_heading("Bibliography")
    assert not is_references_heading("Reference implementation")


def test_split_entries_numbered():
    block = "[1] A. Smith. Title one. Venue, 2020.\n[2] B. Jones. Title two. J. Foo, 2021."
    entries = split_entries(block)
    assert len(entries) == 2
    assert entries[0].startswith("A. Smith")


def test_parse_entry_extracts_fields():
    ref = parse_entry(1, "A. Smith and B. Jones. A great title. Journal of Foo, 2020. doi:10.1000/xyz")
    assert ref.order == 1
    assert ref.year == "2020"
    assert ref.doi == "10.1000/xyz"
    assert "A great title" in ref.title
    assert ref.raw_text.startswith("A. Smith")
    assert any("Smith" in a for a in ref.authors)


def test_parse_references_roundtrip():
    refs = parse_references(["X. Y. Title. Venue, 1999."])
    assert refs[0].order == 1
    assert refs[0].year == "1999"
