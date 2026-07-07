from lxml import etree

from scholarflow_ocr.parse.document import Document
from scholarflow_ocr.parse.text import split_name


def _persname(parent, forename: str, surname: str) -> None:
    author = etree.SubElement(parent, "author")
    pers = etree.SubElement(author, "persName")
    if forename:
        etree.SubElement(pers, "forename").text = forename
    if surname:
        etree.SubElement(pers, "surname").text = surname


def render_tei(doc: Document) -> str:
    tei = etree.Element("TEI")

    header = etree.SubElement(tei, "teiHeader")
    file_desc = etree.SubElement(header, "fileDesc")
    title_stmt = etree.SubElement(file_desc, "titleStmt")
    etree.SubElement(title_stmt, "title").text = doc.title

    source_desc = etree.SubElement(file_desc, "sourceDesc")
    bibl = etree.SubElement(source_desc, "biblStruct")
    analytic = etree.SubElement(bibl, "analytic")
    for a in doc.authors:
        _persname(analytic, a.forename, a.surname)
    monogr = etree.SubElement(bibl, "monogr")
    imprint = etree.SubElement(monogr, "imprint")
    if doc.year:
        etree.SubElement(imprint, "date").set("when", doc.year)
    if doc.doi:
        idno = etree.SubElement(bibl, "idno")
        idno.set("type", "DOI")
        idno.text = doc.doi

    profile = etree.SubElement(header, "profileDesc")
    abstract = etree.SubElement(profile, "abstract")
    if doc.abstract:
        etree.SubElement(abstract, "p").text = doc.abstract

    text = etree.SubElement(tei, "text")
    body = etree.SubElement(text, "body")
    for s in doc.sections:
        div = etree.SubElement(body, "div")
        head = etree.SubElement(div, "head")
        if s.number:
            head.set("n", s.number)
        if s.coords:
            head.set("coords", s.coords.tei())
        head.text = s.heading
        for para in s.paragraphs:
            p = etree.SubElement(div, "p")
            if para.coords:
                p.set("coords", para.coords.tei())
            p.text = para.text
    for f in doc.figures:
        fig = etree.SubElement(body, "figure")
        if f.kind == "table":
            fig.set("type", "table")
        if f.coords:
            fig.set("coords", f.coords.tei())
        etree.SubElement(fig, "head").text = f.label
        etree.SubElement(fig, "figDesc").text = f.caption

    back = etree.SubElement(text, "back")
    back_div = etree.SubElement(back, "div")
    list_bibl = etree.SubElement(back_div, "listBibl")
    for r in doc.references:
        bs = etree.SubElement(list_bibl, "biblStruct")
        r_analytic = etree.SubElement(bs, "analytic")
        if r.title:
            etree.SubElement(r_analytic, "title").text = r.title
        for name in r.authors:
            fore, sur = split_name(name)
            _persname(r_analytic, fore, sur)
        r_monogr = etree.SubElement(bs, "monogr")
        if r.venue:
            etree.SubElement(r_monogr, "title").text = r.venue
        r_imprint = etree.SubElement(r_monogr, "imprint")
        if r.year:
            etree.SubElement(r_imprint, "date").set("when", r.year)
        if r.doi:
            idn = etree.SubElement(bs, "idno")
            idn.set("type", "DOI")
            idn.text = r.doi

    return etree.tostring(tei, pretty_print=True, encoding="unicode")
