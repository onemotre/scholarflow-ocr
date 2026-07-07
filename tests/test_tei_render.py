from lxml import etree

from scholarflow_ocr.parse.coords import Coords
from scholarflow_ocr.parse.document import (
    Author, Document, Figure, Paragraph, Reference, Section,
)
from scholarflow_ocr.tei.render import render_tei


def _doc() -> Document:
    return Document(
        title="A Title",
        abstract="An abstract.",
        doi="10.1/xyz",
        year="2024",
        authors=(Author("Jane", "Public"),),
        sections=(
            Section("2.1", "Method", (Paragraph("Body.", Coords(1, 1, 2, 3, 4)),), Coords(1, 5, 6, 7, 8)),
        ),
        figures=(Figure("figure", "Figure 1", "A caption.", Coords(2, 1, 2, 3, 4)),),
        references=(Reference(1, "Ref title", ("A. Smith",), "A Venue", "2020", "10.2/abc", "raw"),),
    )


def test_render_tei_paths():
    xml = render_tei(_doc())
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.findtext("teiHeader/fileDesc/titleStmt/title") == "A Title"
    assert root.findtext("teiHeader/profileDesc/abstract/p") == "An abstract."
    head = root.find("text/body/div/head")
    assert head.get("n") == "2.1"
    assert head.get("coords") == "1,5.00,6.00,7.00,8.00"
    assert head.text == "Method"
    assert root.find("text/body/div/p").get("coords") == "1,1.00,2.00,3.00,4.00"
    fig = root.find("text/body/figure")
    assert fig.findtext("head") == "Figure 1"
    assert fig.findtext("figDesc") == "A caption."
    idno = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/idno")
    assert idno.get("type") == "DOI" and idno.text == "10.1/xyz"
