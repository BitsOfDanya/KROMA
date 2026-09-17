import math
import random
from dataclasses import dataclass

from kroma_geo.measure import (
    bearing_deg,
    destination,
    haversine_km,
    point_in_ring,
    polygon_area_ha,
)

from app.models.geometry import Position, Ring


@dataclass(frozen=True)
class ShapeNoise:
    amplitudes: tuple[float, ...]
    phases: tuple[float, ...]

    @classmethod
    def seeded(cls, seed: int, roughness: float = 1.0) -> "ShapeNoise":
        rng = random.Random(seed)
        amplitudes = tuple(
            roughness * base * rng.uniform(0.7, 1.3) for base in (0.08, 0.055, 0.04, 0.03, 0.02)
        )
        phases = tuple(rng.uniform(0, math.tau) for _ in amplitudes)
        return cls(amplitudes, phases)

    def factor(self, theta: float) -> float:
        return 1 + sum(
            amplitude * math.sin((index + 2) * theta + phase)
            for index, (amplitude, phase) in enumerate(
                zip(self.amplitudes, self.phases, strict=True)
            )
        )


def _close(ring: list[Position]) -> Ring:
    return [*ring, ring[0]]


def _radial_ring(origin: Position, radius_at: list[float], vertices: int) -> list[Position]:
    return [
        destination(origin, index * 360 / vertices, radius_at[index]) for index in range(vertices)
    ]


def _scaled_to_area(
    origin: Position, unit_radii: list[float], target_ha: float
) -> tuple[Ring, list[float]]:
    vertices = len(unit_radii)
    unit_ring = _close(_radial_ring(origin, unit_radii, vertices))
    unit_area = polygon_area_ha([unit_ring])
    scale = math.sqrt(target_ha / unit_area)
    radii = [radius * scale for radius in unit_radii]
    return _close(_radial_ring(origin, radii, vertices)), radii


def fire_perimeter(
    ignition: Position,
    direction_deg: float,
    area_ha: float,
    eccentricity: float,
    noise: ShapeNoise,
    vertices: int = 64,
) -> Ring:
    unit_radii = []
    for index in range(vertices):
        theta = math.radians(index * 360 / vertices)
        relative = theta - math.radians(direction_deg)
        ellipse = (1 - eccentricity**2) / (1 - eccentricity * math.cos(relative))
        unit_radii.append(ellipse * noise.factor(theta))
    ring, _ = _scaled_to_area(ignition, unit_radii, area_ha)
    return ring


def active_front(
    ring: Ring, ignition: Position, direction_deg: float, half_angle_deg: float = 62
) -> list[Position]:
    points = ring[:-1]
    selected = [
        abs((bearing_deg(ignition, point) - direction_deg + 540) % 360 - 180) <= half_angle_deg
        for point in points
    ]
    if all(selected) or not any(selected):
        return points
    start = next(
        index for index in range(len(points)) if selected[index] and not selected[index - 1]
    )
    front: list[Position] = []
    for offset in range(len(points)):
        index = (start + offset) % len(points)
        if not selected[index]:
            break
        front.append(points[index])
    return front


def blob(
    center: Position,
    area_ha: float,
    noise: ShapeNoise,
    elongation: float = 0.0,
    axis_deg: float = 0.0,
    vertices: int = 56,
) -> Ring:
    unit_radii = []
    for index in range(vertices):
        theta = math.radians(index * 360 / vertices)
        stretch = 1 + elongation * math.cos(2 * (theta - math.radians(axis_deg)))
        unit_radii.append(stretch * noise.factor(theta))
    ring, _ = _scaled_to_area(center, unit_radii, area_ha)
    return ring


def nested_zone(outer: Ring, center: Position, target_ha: float, noise: ShapeNoise) -> Ring:
    points = outer[:-1]
    vertices = len(points)
    outer_radii = [haversine_km(center, point) for point in points]
    shaped = [
        outer_radii[index] * noise.factor(math.radians(index * 360 / vertices) * 1.7)
        for index in range(vertices)
    ]
    ring, radii = _scaled_to_area(center, shaped, target_ha)
    clipped = [min(radius, outer_radii[index] * 0.94) for index, radius in enumerate(radii)]
    return _close(_radial_ring(center, clipped, vertices))


def sample_in_ring(
    rng: random.Random,
    ring: Ring,
    count: int,
    bias_origin: Position | None = None,
    bias_direction_deg: float | None = None,
) -> list[Position]:
    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]
    min_lon, max_lon, min_lat, max_lat = min(lons), max(lons), min(lats), max(lats)
    points: list[Position] = []
    attempts = 0
    while len(points) < count and attempts < count * 400:
        attempts += 1
        candidate = (rng.uniform(min_lon, max_lon), rng.uniform(min_lat, max_lat))
        if not point_in_ring(candidate, ring):
            continue
        if bias_origin is not None and bias_direction_deg is not None:
            offset = math.radians(bearing_deg(bias_origin, candidate) - bias_direction_deg)
            weight = 0.25 + 0.75 * max(0.0, math.cos(offset))
            if rng.random() > weight:
                continue
        points.append((round(candidate[0], 5), round(candidate[1], 5)))
    return points


def scatter_around(
    rng: random.Random, center: Position, radius_km: float, count: int
) -> list[Position]:
    points = []
    for _ in range(count):
        distance = radius_km * math.sqrt(rng.random())
        point = destination(center, rng.uniform(0, 360), distance)
        points.append((round(point[0], 5), round(point[1], 5)))
    return points
