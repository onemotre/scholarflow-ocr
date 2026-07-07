from scholarflow_ocr.parse.coords import Coords, translate


def test_translate_scales_pixels_to_points():
    # image is 1000x1400 px; page is 500x700 pt → scale 0.5 on both axes
    c = translate(2, (100, 200, 300, 40), w_px=1000, h_px=1400, w_pt=500, h_pt=700)
    assert c == Coords(2, 50.0, 100.0, 150.0, 20.0)


def test_translate_zero_dimension_returns_none():
    assert translate(1, (0, 0, 10, 10), w_px=0, h_px=1400, w_pt=500, h_pt=700) is None


def test_coords_tei_format():
    assert Coords(3, 12.345, 6.0, 7.5, 8.0).tei() == "3,12.35,6.00,7.50,8.00"
