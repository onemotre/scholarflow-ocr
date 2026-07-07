from scholarflow_ocr.ocr.models import LayoutBox, Page
from scholarflow_ocr.parse.document import Author
from scholarflow_ocr.parse.frontmatter import extract_frontmatter


def test_extract_frontmatter():
    page = Page(
        page_num=1, width_px=1000, height_px=1400,
        layouts=(
            LayoutBox(1, "title", "A Great Paper", (0, 10, 400, 30)),
            LayoutBox(2, "text", "Jane Q Public, John Doe", (0, 50, 400, 20)),
            LayoutBox(3, "title", "Abstract", (0, 90, 200, 20)),
            LayoutBox(4, "text", "We present something. doi:10.1145/1234567 (2024)", (0, 120, 400, 60)),
        ),
    )
    fm = extract_frontmatter(page)
    assert fm.title == "A Great Paper"
    assert fm.abstract.startswith("We present something.")
    assert fm.authors == (Author("Jane Q", "Public"), Author("John", "Doe"))
    assert fm.doi == "10.1145/1234567"
    assert fm.year == "2024"


def test_extract_frontmatter_author_forename():
    page = Page(1, 1000, 1400, (
        LayoutBox(1, "title", "T", (0, 0, 10, 10)),
        LayoutBox(2, "text", "John Doe", (0, 20, 10, 10)),
        LayoutBox(3, "title", "Abstract", (0, 40, 10, 10)),
        LayoutBox(4, "text", "Body.", (0, 60, 10, 10)),
    ))
    fm = extract_frontmatter(page)
    assert fm.authors == (Author("John", "Doe"),)
