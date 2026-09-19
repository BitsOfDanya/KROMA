from __future__ import annotations

import io
import zipfile
from typing import Any

import shapefile
from shapely.geometry import shape
from shapely.geometry.polygon import orient

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
POLYGON_FIELDS = (
    ("contour_id", "C", 48, 0),
    ("class_id", "N", 4, 0),
    ("severity", "C", 12, 0),
    ("area_ha", "N", 18, 4),
    ("scene_id", "C", 48, 0),
    ("model_ver", "C", 64, 0),
    ("source", "C", 48, 0),
)
POINT_FIELDS = (
    ("point_id", "C", 48, 0),
    ("scene_id", "C", 48, 0),
    ("confidence", "N", 10, 4),
    ("model_ver", "C", 64, 0),
    ("source", "C", 48, 0),
)


def _text(value: Any, size: int) -> str:
    return ("" if value is None else str(value))[:size]


def _rings(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    shapely_geometry = shape(geometry)
    polygons = (
        list(shapely_geometry.geoms)
        if shapely_geometry.geom_type == "MultiPolygon"
        else [shapely_geometry]
    )
    rings: list[list[tuple[float, float]]] = []
    for polygon in polygons:
        oriented = orient(polygon, sign=-1.0)
        rings.append(list(oriented.exterior.coords))
        rings.extend(list(interior.coords) for interior in oriented.interiors)
    return rings


def shapefile_zip(features: list[dict[str, Any]], layer_name: str) -> bytes:
    if not features:
        raise ValueError("no features to export")
    geometry_type = features[0]["geometry"]["type"]
    is_point = geometry_type == "Point"
    fields = POINT_FIELDS if is_point else POLYGON_FIELDS
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(
        shp=shp,
        shx=shx,
        dbf=dbf,
        shapeType=shapefile.POINT if is_point else shapefile.POLYGON,
        encoding="utf-8",
    )
    for name, kind, size, decimal in fields:
        writer.field(name, kind, size, decimal)
    for feature in features:
        properties = feature["properties"]
        if is_point:
            longitude, latitude = feature["geometry"]["coordinates"][:2]
            writer.point(longitude, latitude)
            writer.record(
                _text(properties.get("id"), 48),
                _text(properties.get("scene_id"), 48),
                float(properties.get("confidence") or 0.0),
                _text(properties.get("model_version"), 64),
                _text(properties.get("source"), 48),
            )
        else:
            writer.poly(_rings(feature["geometry"]))
            writer.record(
                _text(properties.get("id"), 48),
                int(properties.get("class_id") or 0),
                _text(properties.get("severity"), 12),
                float(properties.get("area_ha") or 0.0),
                _text(properties.get("scene_id") or properties.get("burn_event_id"), 48),
                _text(properties.get("model_version") or properties.get("processing_version"), 64),
                _text(properties.get("source"), 48),
            )
    writer.close()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{layer_name}.shp", shp.getvalue())
        bundle.writestr(f"{layer_name}.shx", shx.getvalue())
        bundle.writestr(f"{layer_name}.dbf", dbf.getvalue())
        bundle.writestr(f"{layer_name}.prj", WGS84_PRJ)
        bundle.writestr(f"{layer_name}.cpg", "UTF-8")
    return archive.getvalue()
