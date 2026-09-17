import math
from collections.abc import Sequence

EARTH_RADIUS_KM = 6371.0088

Position = tuple[float, float]
BBox = tuple[float, float, float, float]


def haversine_km(a: Position, b: Position) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: Position, b: Position) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination(origin: Position, bearing: float, distance_km: float) -> Position:
    lon1, lat1 = map(math.radians, origin)
    theta = math.radians(bearing)
    delta = distance_km / EARTH_RADIUS_KM
    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta) + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    return (round((math.degrees(lon2) + 540) % 360 - 180, 6), round(math.degrees(lat2), 6))


def ring_area_ha(ring: Sequence[Position]) -> float:
    if len(ring) < 4:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:], strict=False):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area_km2 = abs(total * EARTH_RADIUS_KM**2 / 2)
    return area_km2 * 100


def polygon_area_ha(rings: Sequence[Sequence[Position]]) -> float:
    if not rings:
        return 0.0
    outer = ring_area_ha(rings[0])
    holes = sum(ring_area_ha(ring) for ring in rings[1:])
    return max(0.0, outer - holes)


def distance_to_segment_km(point: Position, start: Position, end: Position) -> float:
    lat0 = math.radians(point[1])
    kx = 111.32 * math.cos(lat0)
    ky = 110.574
    px, py = 0.0, 0.0
    ax, ay = (start[0] - point[0]) * kx, (start[1] - point[1]) * ky
    bx, by = (end[0] - point[0]) * kx, (end[1] - point[1]) * ky
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(cx - px, cy - py)


def distance_to_line_km(point: Position, line: Sequence[Position]) -> float:
    if len(line) == 1:
        return haversine_km(point, line[0])
    return min(distance_to_segment_km(point, a, b) for a, b in zip(line, line[1:], strict=False))


def bbox_of(positions: Sequence[Position]) -> BBox:
    lons = [p[0] for p in positions]
    lats = [p[1] for p in positions]
    return (min(lons), min(lats), max(lons), max(lats))


def bbox_intersects(a: BBox, b: BBox) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def point_in_bbox(point: Position, bbox: BBox) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def point_in_ring(point: Position, ring: Sequence[Position]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing:
                inside = not inside
    return inside


def ring_centroid(ring: Sequence[Position]) -> Position:
    points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return (round(lon, 5), round(lat, 5))
