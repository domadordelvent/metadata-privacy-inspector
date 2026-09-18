from gps_extractor import _to_decimal
import pytest


def test_north_east_coordinates_are_positive():
    assert _to_decimal((41, 23, 10), "N") > 0
    assert _to_decimal((2, 10, 20), "E") > 0


def test_south_west_coordinates_are_negative():
    assert _to_decimal((3, 7, 29), "S") < 0
    assert _to_decimal((38, 16, 46), "W") < 0


def test_coordinate_conversion():
    result = _to_decimal((3, 7, 29.3885895404), "S")

    assert result == pytest.approx(-3.12483016)
