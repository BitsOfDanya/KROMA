from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pyproj import CRS, Transformer
from shapely import box, make_valid
from shapely.geometry import Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity

GeoJSON = dict[str, Any]
BBox = tuple[float, float, float, float]


class GeometryError(ValueError):
    """Raised when a prepared geometry cannot be used without changing its meaning."""


def _geometry(value: GeoJSON | BaseGeometry) -> BaseGeometry:
    geometry = value if isinstance(value, BaseGeometry) else shape(value)
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise GeometryError(f"expected Polygon or MultiPolygon, got {geometry.geom_type}")
    return geometry


def validate_geometry(value: GeoJSON | BaseGeometry, *, repair: bool = False) -> BaseGeometry:
    geometry = _geometry(value)
    if geometry.is_empty:
        raise GeometryError("geometry is empty")
    if geometry.is_valid:
        return geometry
    if not repair:
        raise GeometryError(f"invalid geometry: {explain_validity(geometry)}")
    repaired = make_valid(geometry)
    polygonal = [
        part
        for part in getattr(repaired, "geoms", [repaired])
        if part.geom_type in {"Polygon", "MultiPolygon"}
    ]
    repaired = unary_union(polygonal)
    if repaired.is_empty or not repaired.is_valid:
        raise GeometryError(f"geometry cannot be repaired: {explain_validity(repaired)}")
    before = abs(geometry.area)
    if before and abs(repaired.area - before) / before > 1e-6:
        raise GeometryError("repair changes geometry area materially")
    return repaired


def canonical_geojson(value: GeoJSON | BaseGeometry) -> GeoJSON:
    geometry = _geometry(value)
    if geometry.geom_type == "GeometryCollection":
        geometry = unary_union(
            [part for part in geometry.geoms if part.geom_type in {"Polygon", "MultiPolygon"}]
        )
    return mapping(geometry)  # type: ignore[return-value]


def clip_to_bbox(value: GeoJSON | BaseGeometry, bbox: BBox) -> GeoJSON | None:
    geometry = validate_geometry(value)
    clipped = geometry.intersection(box(*bbox))
    if clipped.is_empty or clipped.area <= 0:
        return None
    if clipped.geom_type not in {"Polygon", "MultiPolygon"}:
        pieces = [
            part
            for part in getattr(clipped, "geoms", [])
            if part.geom_type in {"Polygon", "MultiPolygon"} and part.area > 0
        ]
        if not pieces:
            return None
        clipped = unary_union(pieces)
    return canonical_geojson(clipped)


def reproject_geometry(
    value: GeoJSON | BaseGeometry, source_crs: str, target_crs: str
) -> BaseGeometry:
    transformer = Transformer.from_crs(
        CRS.from_user_input(source_crs), CRS.from_user_input(target_crs), always_xy=True
    )
    return transform(transformer.transform, _geometry(value))


def geometry_area_ha(
    value: GeoJSON | BaseGeometry,
    *,
    source_crs: str = "EPSG:4326",
    area_crs: str = "EPSG:6933",
) -> float:
    geometry = validate_geometry(value)
    projected = reproject_geometry(geometry, source_crs, area_crs)
    return projected.area / 10_000


def intersection_area_ha(
    left: GeoJSON | BaseGeometry,
    right: GeoJSON | BaseGeometry,
    *,
    source_crs: str = "EPSG:4326",
    area_crs: str = "EPSG:6933",
) -> float:
    intersection = _geometry(left).intersection(_geometry(right))
    if intersection.is_empty or intersection.area <= 0:
        return 0.0
    projected = reproject_geometry(intersection, source_crs, area_crs)
    return projected.area / 10_000


def bbox_geometry(bbox: BBox) -> GeoJSON:
    return canonical_geojson(box(*bbox))


def assert_non_overlapping(
    geometries: Sequence[GeoJSON | BaseGeometry],
    *,
    tolerance_ha: float = 1e-9,
    source_crs: str = "EPSG:4326",
    area_crs: str = "EPSG:6933",
) -> None:
    values = [validate_geometry(value) for value in geometries]
    for index, left in enumerate(values):
        for right in values[index + 1 :]:
            if (
                intersection_area_ha(left, right, source_crs=source_crs, area_crs=area_crs)
                > tolerance_ha
            ):
                raise GeometryError("polygon classes overlap by positive area")


def vectorize_class_mask(
    mask: Sequence[Sequence[int]],
    transform_values: tuple[float, float, float, float, float, float],
    *,
    valid_classes: tuple[int, ...] = (1, 2, 3),
    nodata: int | None = None,
) -> dict[int, GeoJSON]:
    """Vectorize a small categorical raster without depending on rasterio.

    ``transform_values`` follows GDAL's affine order ``a,b,c,d,e,f``. Rotated
    cells are supported and adjacent pixels are dissolved per class.
    """

    if not mask or not mask[0]:
        raise GeometryError("mask is empty")
    width = len(mask[0])
    if any(len(row) != width for row in mask):
        raise GeometryError("mask rows have different widths")
    a, b, c, d, e, f = transform_values

    def corner(col: int, row: int) -> tuple[float, float]:
        return (a * col + b * row + c, d * col + e * row + f)

    by_class: dict[int, list[Polygon]] = {class_id: [] for class_id in valid_classes}
    for row, values in enumerate(mask):
        for col, class_id in enumerate(values):
            if nodata is not None and class_id == nodata:
                continue
            if class_id not in valid_classes and class_id != 0:
                raise GeometryError(f"unsupported class_id {class_id}")
            if class_id in by_class:
                by_class[class_id].append(
                    Polygon(
                        [
                            corner(col, row),
                            corner(col + 1, row),
                            corner(col + 1, row + 1),
                            corner(col, row + 1),
                            corner(col, row),
                        ]
                    )
                )
    return {
        class_id: canonical_geojson(unary_union(pixels))
        for class_id, pixels in by_class.items()
        if pixels
    }
