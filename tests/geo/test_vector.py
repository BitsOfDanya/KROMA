import pytest
from kroma_geo.vector import (
    GeometryError,
    assert_non_overlapping,
    clip_to_bbox,
    geometry_area_ha,
    validate_geometry,
    vectorize_class_mask,
)


def test_one_20m_pixel_and_half_clip() -> None:
    zones = vectorize_class_mask([[1]], (20, 0, 0, 0, -20, 20))
    assert geometry_area_ha(
        zones[1], source_crs="EPSG:32645", area_crs="EPSG:32645"
    ) == pytest.approx(0.04)

    half = clip_to_bbox(zones[1], (0, 0, 10, 20))
    assert half is not None
    assert geometry_area_ha(half, source_crs="EPSG:32645", area_crs="EPSG:32645") == pytest.approx(
        0.02
    )


def test_vectorizer_keeps_hole_and_disconnected_parts() -> None:
    mask = [
        [1, 1, 1, 0, 1],
        [1, 0, 1, 0, 0],
        [1, 1, 1, 0, 0],
    ]
    geometry = vectorize_class_mask(mask, (1, 0, 0, 0, -1, 3))[1]
    assert geometry["type"] == "MultiPolygon"
    polygons = geometry["coordinates"]
    assert any(len(polygon) == 2 for polygon in polygons)


def test_touching_is_allowed_but_overlap_is_rejected() -> None:
    left = {"type": "Polygon", "coordinates": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]]}
    touching = {"type": "Polygon", "coordinates": [[(1, 0), (2, 0), (2, 1), (1, 1), (1, 0)]]}
    overlap = {"type": "Polygon", "coordinates": [[(0.5, 0), (2, 0), (2, 1), (0.5, 1), (0.5, 0)]]}

    assert_non_overlapping([left, touching])
    with pytest.raises(GeometryError, match="overlap"):
        assert_non_overlapping([left, overlap])


def test_invalid_self_intersection_is_rejected() -> None:
    bow = {"type": "Polygon", "coordinates": [[(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)]]}
    with pytest.raises(GeometryError, match="invalid"):
        validate_geometry(bow)
