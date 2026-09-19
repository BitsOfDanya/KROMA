import numpy as np
import pytest
from kroma_geo.raster_vector import (
    ChipGeoreference,
    class_features,
    mask_polygon,
    pixel_area_ha,
    point_features,
)

GEOREF = ChipGeoreference(epsg=32637, x_min=500_000.0, y_max=5_400_000.0, gsd_x=20.0, gsd_y=20.0)


def test_area_matches_pixel_count_times_gsd_squared() -> None:
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[5:15, 5:25] = 2
    assert pixel_area_ha(int((mask == 2).sum()), GEOREF) == pytest.approx(8.0)
    geometry = mask_polygon(mask == 2, GEOREF)
    assert geometry.area == pytest.approx(80_000.0)
    features = class_features(
        mask, GEOREF, classes={1: "low", 2: "moderate"}, scene_id="S", model_version="t", source="x"
    )
    assert [f["properties"]["severity"] for f in features] == ["moderate"]
    assert features[0]["properties"]["area_ha"] == pytest.approx(8.0)
    assert features[0]["properties"]["class_area_ha"] == pytest.approx(8.0)


def test_polygon_matches_arbitrary_mask_exactly() -> None:
    rng = np.random.default_rng(3)
    mask = rng.random((64, 64)) > 0.6
    geometry = mask_polygon(mask, GEOREF)
    assert geometry.area == pytest.approx(mask.sum() * 400.0)


def test_disjoint_regions_become_separate_polygons_with_holes_kept() -> None:
    mask = np.zeros((30, 30), dtype=np.uint8)
    mask[2:6, 2:6] = 1
    mask[10:20, 10:20] = 1
    mask[13:16, 13:16] = 0
    features = class_features(
        mask, GEOREF, classes={1: "low"}, scene_id="S", model_version="t", source="x"
    )
    areas = sorted(f["properties"]["area_ha"] for f in features)
    assert areas == pytest.approx([16 * 0.04, (100 - 9) * 0.04])


def test_features_are_wgs84_and_north_up() -> None:
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[0:5, 0:5] = 3
    (feature,) = class_features(
        mask, GEOREF, classes={3: "high"}, scene_id="S", model_version="t", source="x"
    )
    lons = [c[0] for c in feature["geometry"]["coordinates"][0]]
    lats = [c[1] for c in feature["geometry"]["coordinates"][0]]
    assert 35.0 < min(lons) < max(lons) < 40.0
    assert 48.0 < min(lats) < max(lats) < 49.0


def test_point_features_are_pixel_centres_and_capped() -> None:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[3, 4] = 1
    mask[10:12, 10:12] = 1
    points = point_features(mask, GEOREF, scene_id="S", model_version="t", source="x", limit=3)
    assert len(points) == 3
    assert {p["properties"]["row"] for p in points} <= {3, 10, 11}


def test_neighboring_projected_classes_remain_disjoint() -> None:
    import numpy as np
    from kroma_geo.raster_vector import ChipGeoreference, class_features
    from kroma_geo.vector import assert_non_overlapping

    mask = np.ones((30, 30), dtype=np.uint8)
    mask[10:20, 10:20] = 2
    georef = ChipGeoreference(32637, 614400, 5263360, 20, 20)
    features = class_features(
        mask,
        georef,
        classes={1: "low", 2: "moderate"},
        scene_id="test",
        model_version="test",
        source="synthetic",
    )
    assert_non_overlapping([f["geometry"] for f in features])
    assert sum(f["properties"]["area_ha"] for f in features) == 36
