import io

from pypdf import PdfReader


def page_point_sizes(pdf: bytes) -> list[tuple[float, float]]:
    reader = PdfReader(io.BytesIO(pdf))
    sizes: list[tuple[float, float]] = []
    for page in reader.pages:
        box = page.mediabox
        sizes.append((float(box.width), float(box.height)))
    return sizes
