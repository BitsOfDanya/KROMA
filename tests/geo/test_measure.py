import pytest
from kroma_geo.measure import (
    bbox_intersects,
    bearing_deg,
    destination,
    distance_to_line_km,
    haversine_km,
    polygon_area_ha,
)


def test_haversine_krasnoyarsk_to_kodinsk() -> None:
    krasnoyarsk = (92.8932, 56.0153)
    kodinsk = (99.1797, 58.6036)
    assert haversine_km(krasnoyarsk, kodinsk) == pytest.approx(474, rel=0.01)


def test_destination_roundtrip() -> None:
    origin = (99.4, 58.5)
    target = destination(origin, 45, 10)
    assert haversine_km(origin, target) == pytest.approx(10, rel=1e-3)
    assert bearing_deg(origin, target) == pytest.approx(45, abs=0.5)


def test_polygon_area_of_one_km_square_near_equator() -> None:
    d = 1 / 111.32
    ring = [(0.0, 0.0), (d, 0.0), (d, d), (0.0, d), (0.0, 0.0)]
    assert polygon_area_ha([ring]) == pytest.approx(100, rel=0.01)


def test_distance_to_line_and_bbox() -> None:
    line = [(99.0, 58.0), (100.0, 58.0)]
    assert distance_to_line_km((99.5, 58.1), line) == pytest.approx(11.06, rel=0.02)
    assert bbox_intersects((90, 50, 100, 60), (95, 55, 110, 70))
    assert not bbox_intersects((90, 50, 100, 60), (101, 55, 110, 70))


def test_point_in_ring() -> None:
    from kroma_geo.measure import point_in_ring, ring_centroid

    ring = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0), (0.0, 0.0)]
    assert point_in_ring((1.0, 1.0), ring)
    assert not point_in_ring((3.0, 1.0), ring)
    assert ring_centroid(ring) == (1.0, 1.0)
