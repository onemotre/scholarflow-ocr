from lxml import etree

from scholarflow_ocr.parse.coords import Coords
from scholarflow_ocr.parse.document import (
    Author, Document, Figure, Paragraph, Reference, Section,
)
from scholarflow_ocr.tei.render import render_tei


def _first_page_of_coords(coords: str) -> int:
    # Reproduces grobid.go parsePage: first integer of "page,x,y,w,h".
    return int(coords.split(",")[0])


def test_server_would_extract_all_fields():
    doc = Document(
        title="Contract Paper",
        abstract="Abstract body.",
        doi="10.1/aaa",
        year="2022",
        authors=(Author("Grace", "Hopper"),),
        sections=(Section("1", "Intro", (Paragraph("Text.", Coords(3, 1, 1, 1, 1)),), Coords(3, 1, 1, 1, 1)),),
        figures=(Figure("table", "Table 1", "Cap.", Coords(4, 1, 1, 1, 1)),),
        references=(Reference(1, "R Title", ("I. Newton",), "Nature", "1687", "10.9/zzz", "raw"),),
    )
    root = etree.fromstring(render_tei(doc).encode("utf-8"))

    # Header (grobid.go: title, abstract, analytic authors, DOI, year)
    assert root.findtext("teiHeader/fileDesc/titleStmt/title") == "Contract Paper"
    assert root.findtext("teiHeader/profileDesc/abstract/p") == "Abstract body."
    pers = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/analytic/author/persName")
    assert pers.findtext("forename") == "Grace"
    assert pers.findtext("surname") == "Hopper"
    idno = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/idno")
    assert idno.get("type") == "DOI" and idno.text == "10.1/aaa"
    when = root.find("teiHeader/fileDesc/sourceDesc/biblStruct/monogr/imprint/date").get("when")
    assert when.startswith("2022")

    # Body div/head@n + coords page, p, figure
    div = root.find("text/body/div")
    assert div.find("head").get("n") == "1"
    assert _first_page_of_coords(div.find("head").get("coords")) == 3
    assert div.findtext("p") == "Text."
    fig = root.find("text/body/figure")
    assert fig.get("type") == "table"
    assert fig.findtext("head") == "Table 1"
    assert fig.findtext("figDesc") == "Cap."
    assert _first_page_of_coords(fig.get("coords")) == 4

    # References under text/back/div/listBibl/biblStruct
    bibl = root.find("text/back/div/listBibl/biblStruct")
    assert bibl.findtext("analytic/title") == "R Title"
    assert bibl.find("analytic/author/persName/surname").text == "Newton"
    assert bibl.findtext("monogr/title") == "Nature"
    assert bibl.find("monogr/imprint/date").get("when") == "1687"
    assert bibl.find("idno").get("type") == "DOI"
