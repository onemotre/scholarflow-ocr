from dataclasses import dataclass


@dataclass(frozen=True)
class Coords:
    page: int
    x: float
    y: float
    w: float
    h: float

    def tei(self) -> str:
        return f"{self.page},{self.x:.2f},{self.y:.2f},{self.w:.2f},{self.h:.2f}"


def translate(
    page: int,
    box: tuple[float, float, float, float],
    w_px: float,
    h_px: float,
    w_pt: float,
    h_pt: float,
) -> Coords | None:
    if w_px <= 0 or h_px <= 0 or w_pt <= 0 or h_pt <= 0:
        return None
    sx = w_pt / w_px
    sy = h_pt / h_px
    x, y, w, h = box
    return Coords(page, x * sx, y * sy, w * sx, h * sy)
