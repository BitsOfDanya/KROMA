import json
import runpy
from datetime import date
from pathlib import Path

from kroma_geo.context import (
    RegionIndex,
    feature_distance_km,
    geometry_bboxes,
    in_aoi,
    nearest_context,
)


def test_region_assignment_respects_hole_and_multipolygon(tmp_path) -> None:
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
                [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]],
            ],
            [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
        ],
    }
    path = tmp_path / "regions.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"shapeISO": "RU-X", "shapeName": "Example"},
                        "geometry": geometry,
                    }
                ],
            }
        )
    )
    regions = RegionIndex.from_geojson(path)
    assert regions.assign(3, 3).code == "RU-X"
    assert regions.assign(10.5, 10.5).code == "RU-X"
    assert regions.assign(1.5, 1.5) is None
    assert in_aoi(10.5, 10.5, geometry=geometry)
    assert not in_aoi(1.5, 1.5, geometry=geometry)


def test_nearest_context_uses_geometry_distance() -> None:
    features = [
        {
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [0, 1]]},
            "properties": {"category": "road", "name": "west"},
        },
        {
            "geometry": {"type": "Point", "coordinates": [2, 0.5]},
            "properties": {"category": "settlement", "name": "east"},
        },
    ]
    context = nearest_context((0.1, 0.5), features, ["road", "settlement", "power_line"])
    assert context["road"]["distance_km"] < context["settlement"]["distance_km"]
    assert context["power_line"] is None
    assert feature_distance_km((0.1, 0.5), features[0]["geometry"]) > 0


def test_antimeridian_aoi_has_narrow_download_boxes() -> None:
    geometry = {
        "type": "Polygon",
        "coordinates": [[[179, 60], [-179, 60], [-179, 61], [179, 61], [179, 60]]],
    }
    boxes = geometry_bboxes(geometry)
    assert boxes == ((179, 60, 180.0, 61), (-180.0, 60, -179, 61))
    assert in_aoi(179.5, 60.5, geometry=geometry)
    assert in_aoi(-179.5, 60.5, geometry=geometry)
    assert not in_aoi(0, 60.5, geometry=geometry)


def test_antimeridian_region_assignment_works_with_optional_shapely(tmp_path) -> None:
    geometry = {
        "type": "Polygon",
        "coordinates": [[[179, 60], [-179, 60], [-179, 61], [179, 61], [179, 60]]],
    }
    path = tmp_path / "dateline.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"code": "RU-X", "name": "Dateline"},
                        "geometry": geometry,
                    }
                ],
            }
        )
    )
    index = RegionIndex.from_geojson(path)
    assert index.assign(179.5, 60.5).code == "RU-X"
    assert index.assign(-179.5, 60.5).code == "RU-X"
    assert index.assign(0, 60.5) is None


def test_osm_adapter_preserves_historical_query_and_context_geometry() -> None:
    adapter = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/ingestion/osm_context.py")
    )
    query = adapter["build_query"]((86, 54, 86.2, 54.2), date(2023, 7, 12), ["road"])
    assert '[date:"2023-07-12T23:59:59Z"]' in query
    assert "(54,86,54.2,86.2)" in query
    features = adapter["to_features"](
        [
            {
                "type": "way",
                "id": 42,
                "tags": {"highway": "primary", "name": "road"},
                "geometry": [{"lon": 86, "lat": 54}, {"lon": 86.1, "lat": 54.1}],
            }
        ]
    )
    assert features[0]["geometry"]["type"] == "LineString"
    assert nearest_context((86, 54), features, ["road"])["road"]["distance_km"] == 0
