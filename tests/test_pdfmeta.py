from pathlib import Path

from scholarflow_ocr.pdfmeta import page_point_sizes


def test_page_point_sizes():
    # Use real minimal one-page PDF (US Letter size: 612x792 pt)
    pdf_path = Path(__file__).parent / "fixtures" / "onepage.pdf"
    pdf_bytes = pdf_path.read_bytes()
    sizes = page_point_sizes(pdf_bytes)
    assert sizes == [(612.0, 792.0)]
