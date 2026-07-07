from scholarflow_ocr.ocr.models import LayoutBox, Page
from scholarflow_ocr.parse.layout import build_body, section_number
from scholarflow_ocr.parse.text import split_name


def test_section_number_splits_leading_numbering():
    assert section_number("2.1 Motion Track") == ("2.1", "Motion Track")
    assert section_number("Introduction") == ("", "Introduction")


def test_section_number_strips_trailing_period():
    assert section_number("1. Introduction") == ("1", "Introduction")
    assert section_number("2.1 Motion") == ("2.1", "Motion")
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


def test_build_body_associates_figure_title_with_pending_figure():
    page = Page(
        page_num=1,
        width_px=1000,
        height_px=1400,
        layouts=(
            LayoutBox(1, "paragraph_title", "1. Introduction", (0, 0, 200, 20)),
            LayoutBox(2, "image", "", (0, 30, 300, 300)),
            LayoutBox(3, "chart", "", (0, 30, 300, 300)),
            LayoutBox(4, "figure_title", "Figure 1. Overview. We present a framework.", (0, 340, 300, 30)),
        ),
    )
    sizes = [(500.0, 700.0)]
    sections, figures, next_order = build_body(page, sizes, base_order=0)
    assert len(figures) == 2
    # The figure_title is associated with the most recent figure that still
    # has an empty caption (i.e. the "chart" box), not the first ("image").
    assert figures[0].caption == ""
    assert figures[1].caption.startswith("Figure 1. Overview.")
    assert figures[1].label == "Figure 1"


def test_build_body_skips_abstract_type():
    page = Page(
        page_num=1,
        width_px=1000,
        height_px=1400,
        layouts=(
            LayoutBox(1, "paragraph_title", "1. Introduction", (0, 0, 200, 20)),
            LayoutBox(2, "abstract", "This should not become a section or paragraph.", (0, 30, 400, 40)),
            LayoutBox(3, "text", "Real body text.", (0, 70, 400, 40)),
        ),
    )
    sizes = [(500.0, 700.0)]
    sections, figures, next_order = build_body(page, sizes, base_order=0)
    assert len(sections) == 1
    assert sections[0].heading == "Introduction"
    assert [p.text for p in sections[0].paragraphs] == ["Real body text."]
    assert figures == []
