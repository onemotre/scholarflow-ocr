from scholarflow_ocr.ocr.models import LayoutBox, Page
from scholarflow_ocr.parse.layout import build_body, section_number
from scholarflow_ocr.parse.text import split_name


def test_section_number_splits_leading_numbering():
    assert section_number("2.1 Motion Track") == ("2.1", "Motion Track")
    assert section_number("Introduction") == ("", "Introduction")


def test_split_name():
    assert split_name("Jane Q Public") == ("Jane Q", "Public")
    assert split_name("Plato") == ("", "Plato")


def test_build_body_makes_sections_and_figures():
    page = Page(
        page_num=1,
        width_px=1000,
        height_px=1400,
        layouts=(
            LayoutBox(1, "title", "2 Method", (0, 100, 200, 20)),
            LayoutBox(2, "text", "We do things.", (0, 130, 400, 40)),
            LayoutBox(3, "image", "Figure 1: our pipeline.", (0, 200, 300, 300)),
        ),
    )
    sizes = [(500.0, 700.0)]  # scale 0.5
    sections, figures, next_order = build_body(page, sizes, base_order=0)
    assert len(sections) == 1
    assert sections[0].number == "2"
    assert sections[0].heading == "Method"
    assert sections[0].paragraphs[0].text == "We do things."
    assert sections[0].coords is not None and sections[0].coords.page == 1
    assert len(figures) == 1
    assert figures[0].kind == "figure"
    assert figures[0].label == "Figure 1"
    assert figures[0].caption == "Figure 1: our pipeline."
    assert next_order == 1
