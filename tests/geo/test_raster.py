import pytest
from kroma_geo.raster import (
    dominant_land_cover,
    land_cover_at,
    land_cover_composition,
    nbr,
    ndvi,
)


def test_vegetation_indices_and_dominant_class() -> None:
    assert ndvi(0.8, 0.2) == pytest.approx(0.6)
    assert nbr(0.8, 0.2) == pytest.approx(0.6)
    assert ndvi(0, 0) is None
    assert dominant_land_cover({"forest": 0.75, "water": 0.25}) == "forest"


def test_worldcover_point_and_polygon_on_tiny_raster(tmp_path) -> None:
    numpy = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    path = tmp_path / "cover.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=2,
        width=2,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(0, 2, 1, 1),
        nodata=0,
    ) as dataset:
        dataset.write(numpy.array([[10, 40], [80, 50]], dtype="uint8"), 1)
    geometry = {
        "type": "Polygon",
        "coordinates": [[[0, 1], [2, 1], [2, 2], [0, 2], [0, 1]]],
    }
    assert land_cover_at(path, 0.5, 1.5) == "forest"
    assert land_cover_composition(path, geometry) == {"cropland": 0.5, "forest": 0.5}
