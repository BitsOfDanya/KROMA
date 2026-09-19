import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kroma_geo.measure import (
    bbox_of,
    distance_to_line_km,
    haversine_km,
    point_in_bbox,
    point_in_ring,
)

Position = tuple[float, float]
BBox = tuple[float, float, float, float]


def contains_geometry(geometry: dict[str, Any], point: Position) -> bool:
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        polygons = [geometry["coordinates"]]
    elif geometry_type == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        raise ValueError("AOI geometry must be Polygon or MultiPolygon")

    def in_ring(ring: list[list[float]]) -> bool:
        first = ring[0][0]
        positions = [(first, ring[0][1])]
        for longitude, latitude, *_ in ring[1:]:
            previous = positions[-1][0]
            positions.append((previous + (longitude - previous + 180) % 360 - 180, latitude))
        shifted = first + (point[0] - first + 180) % 360 - 180
        return point_in_ring((shifted, point[1]), positions)

    for polygon in polygons:
        if not polygon:
            continue
        if in_ring(polygon[0]) and not any(in_ring(ring) for ring in polygon[1:]):
            return True
    return False


def geometry_bbox(geometry: dict[str, Any]) -> BBox:
    polygons = (
        [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    )
    positions = [
        tuple(position[:2]) for polygon in polygons for ring in polygon for position in ring
    ]
    if not positions:
        raise ValueError("empty AOI geometry")
    return bbox_of(positions)


def geometry_bboxes(geometry: dict[str, Any]) -> tuple[BBox, ...]:
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI geometry must be Polygon or MultiPolygon")
    polygons = [geometry["coordinates"]] if geometry_type == "Polygon" else geometry["coordinates"]
    boxes = []
    for polygon in polygons:
        positions = [tuple(position[:2]) for ring in polygon for position in ring]
        if not positions:
            continue
        box = bbox_of(positions)
        if box[2] - box[0] <= 180:
            boxes.append(box)
        else:
            positive = [position for position in positions if position[0] >= 0]
            negative = [position for position in positions if position[0] < 0]
            if positive:
                positive_box = bbox_of(positive)
                boxes.append((positive_box[0], box[1], 180.0, box[3]))
            if negative:
                negative_box = bbox_of(negative)
                boxes.append((-180.0, box[1], negative_box[2], box[3]))
    if not boxes:
        raise ValueError("empty AOI geometry")
    return tuple(boxes)


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    geometry: dict[str, Any]
    bbox: BBox
    boxes: tuple[BBox, ...]


class RegionIndex:
    def __init__(self, regions: Iterable[Region]) -> None:
        self.regions = tuple(regions)
        self.by_code = {region.code: region for region in self.regions}
        try:
            from shapely.geometry import shape
            from shapely.prepared import prep
        except ImportError:
            self.prepared = {}
        else:
            self.prepared = {
                region.code: prep(shape(region.geometry))
                for region in self.regions
                if region.bbox[2] - region.bbox[0] <= 180
            }

    def _matches(self, region: Region, point: Position) -> bool:
        if not any(point_in_bbox(point, box) for box in region.boxes):
            return False
        prepared = self.prepared.get(region.code)
        if prepared is not None:
            from shapely.geometry import Point

            return bool(prepared.contains(Point(point)))
        return contains_geometry(region.geometry, point)

    @classmethod
    def from_geojson(cls, path: Path) -> "RegionIndex":
        collection = json.loads(path.read_text(encoding="utf-8"))
        if collection.get("type") != "FeatureCollection":
            raise ValueError("region file must be a GeoJSON FeatureCollection")
        regions = []
        used_codes: set[str] = set()
        for feature in collection["features"]:
            properties = feature.get("properties") or {}
            code = str(
                properties.get("shapeISO")
                or properties.get("code")
                or properties.get("shapeID")
                or ""
            )
            if code in used_codes:
                code = str(properties.get("shapeID") or "")
            name = str(properties.get("shapeName") or properties.get("name") or "")
            if not code or not name or code in used_codes:
                raise ValueError("region feature requires unique code and name")
            geometry = feature["geometry"]
            regions.append(
                Region(code, name, geometry, geometry_bbox(geometry), geometry_bboxes(geometry))
            )
            used_codes.add(code)
        return cls(regions)

    def assign(self, longitude: float, latitude: float) -> Region | None:
        point = longitude, latitude
        for region in self.regions:
            if self._matches(region, point):
                return region
        return None

    def contains(self, code: str, longitude: float, latitude: float) -> bool:
        region = self.by_code[code]
        point = longitude, latitude
        return self._matches(region, point)


def in_aoi(
    longitude: float,
    latitude: float,
    bbox: BBox | None = None,
    geometry: dict[str, Any] | None = None,
) -> bool:
    point = longitude, latitude
    return (bbox is None or point_in_bbox(point, bbox)) and (
        geometry is None or contains_geometry(geometry, point)
    )


def feature_distance_km(point: Position, geometry: dict[str, Any]) -> float:
    geometry_type = geometry["type"]
    coordinates = geometry["coordinates"]
    if geometry_type == "Point":
        return haversine_km(point, tuple(coordinates[:2]))
    if geometry_type == "MultiPoint":
        return min(haversine_km(point, tuple(item[:2])) for item in coordinates)
    if geometry_type == "LineString":
        return distance_to_line_km(point, [tuple(item[:2]) for item in coordinates])
    if geometry_type == "MultiLineString":
        return min(
            distance_to_line_km(point, [tuple(item[:2]) for item in line]) for line in coordinates
        )
    if geometry_type in {"Polygon", "MultiPolygon"}:
        if contains_geometry(geometry, point):
            return 0.0
        polygons = [coordinates] if geometry_type == "Polygon" else coordinates
        return min(
            distance_to_line_km(point, [tuple(item[:2]) for item in ring])
            for polygon in polygons
            for ring in polygon
        )
    raise ValueError(f"unsupported context geometry: {geometry_type}")


def nearest_context(
    point: Position, features: Iterable[dict[str, Any]], categories: Iterable[str]
) -> dict[str, dict[str, Any] | None]:
    nearest: dict[str, dict[str, Any] | None] = {category: None for category in categories}
    for feature in features:
        properties = feature.get("properties") or {}
        category = properties.get("category")
        if category not in nearest:
            continue
        distance = feature_distance_km(point, feature["geometry"])
        existing = nearest[category]
        if existing is None or distance < existing["distance_km"]:
            nearest[category] = {
                "name": properties.get("name"),
                "distance_km": round(distance, 3),
                "properties": properties,
            }
    return nearest
