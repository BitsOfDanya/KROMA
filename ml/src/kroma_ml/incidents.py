import hashlib
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kroma_geo.measure import haversine_km


@dataclass(frozen=True)
class Observation:
    observation_id: str
    longitude: float
    latitude: float
    acquired_at: datetime
    source: str
    satellite: str
    frp_mw: float | None
    source_confidence: str | int | None
    daynight: str | None
    brightness_kelvin: float | None
    scan_km: float | None
    track_km: float | None
    region: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any], region: str | None = None) -> "Observation":
        location = record["location"]
        timestamp = datetime.fromisoformat(record["acquired_at"].replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError("acquired_at requires a timezone")
        return cls(
            observation_id=record["observation_id"],
            longitude=float(location["longitude"]),
            latitude=float(location["latitude"]),
            acquired_at=timestamp,
            source=record["source"],
            satellite=record["satellite"],
            frp_mw=record.get("frp_mw"),
            source_confidence=record.get("source_confidence"),
            daynight=record.get("daynight"),
            brightness_kelvin=record.get("brightness_ti4_kelvin")
            or record.get("brightness_modis_kelvin"),
            scan_km=record.get("scan_km"),
            track_km=record.get("track_km"),
            region=region,
        )


@dataclass(frozen=True)
class Incident:
    incident_id: str
    observation_ids: tuple[str, ...]
    first_seen: datetime
    last_seen: datetime
    longitude: float
    latitude: float
    observation_count: int
    sensor_count: int
    max_frp_mw: float | None
    mean_frp_mw: float | None
    frp_trend_mw_per_day: float | None
    extent_radius_km: float
    region: str | None


@dataclass(frozen=True)
class ClusterResult:
    incidents: tuple[Incident, ...]
    noise_ids: tuple[str, ...]


def _centroid(observations: list[Observation]) -> tuple[float, float]:
    xyz = [
        (
            math.cos(math.radians(item.latitude)) * math.cos(math.radians(item.longitude)),
            math.cos(math.radians(item.latitude)) * math.sin(math.radians(item.longitude)),
            math.sin(math.radians(item.latitude)),
        )
        for item in observations
    ]
    x, y, z = (sum(point[axis] for point in xyz) for axis in range(3))
    return math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, math.hypot(x, y)))


def _summarize(observations: list[Observation]) -> Incident:
    observations.sort(key=lambda item: (item.acquired_at, item.observation_id))
    longitude, latitude = _centroid(observations)
    frps = [item.frp_mw for item in observations if item.frp_mw is not None]
    midpoint = (
        observations[0].acquired_at
        + (observations[-1].acquired_at - observations[0].acquired_at) / 2
    )
    early = [
        item.frp_mw
        for item in observations
        if item.frp_mw is not None and item.acquired_at <= midpoint
    ]
    late = [
        item.frp_mw
        for item in observations
        if item.frp_mw is not None and item.acquired_at > midpoint
    ]
    span_days = (observations[-1].acquired_at - observations[0].acquired_at).total_seconds() / 86400
    trend = (
        (sum(late) / len(late) - sum(early) / len(early)) / span_days
        if early and late and span_days
        else None
    )
    ids = tuple(sorted(item.observation_id for item in observations))
    incident_id = hashlib.sha256("|".join(ids).encode()).hexdigest()[:20]
    regions = {item.region for item in observations if item.region is not None}
    return Incident(
        incident_id=incident_id,
        observation_ids=ids,
        first_seen=observations[0].acquired_at,
        last_seen=observations[-1].acquired_at,
        longitude=longitude,
        latitude=latitude,
        observation_count=len(observations),
        sensor_count=len({item.satellite for item in observations}),
        max_frp_mw=max(frps) if frps else None,
        mean_frp_mw=sum(frps) / len(frps) if frps else None,
        frp_trend_mw_per_day=trend,
        extent_radius_km=max(
            haversine_km((longitude, latitude), (item.longitude, item.latitude))
            for item in observations
        ),
        region=next(iter(regions)) if len(regions) == 1 else None,
    )


def cluster_incidents(
    observations: list[Observation],
    eps_km: float = 5.0,
    time_window_hours: float = 24.0,
    min_samples: int = 2,
) -> ClusterResult:
    if eps_km <= 0 or time_window_hours <= 0 or min_samples < 1:
        raise ValueError("eps_km and time_window_hours must be positive; min_samples >= 1")
    if not observations:
        return ClusterResult((), ())
    ordered = sorted(observations, key=lambda item: (item.acquired_at, item.observation_id))
    lat_step = eps_km / 111.2
    lon_bins = math.ceil(360 / lat_step)
    lon_step = 360 / lon_bins
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, item in enumerate(ordered):
        buckets[
            (
                math.floor((item.latitude + 90) / lat_step),
                math.floor((item.longitude + 180) / lon_step) % lon_bins,
            )
        ].append(index)
    max_seconds = time_window_hours * 3600

    def neighbors(index: int) -> list[int]:
        item = ordered[index]
        y = math.floor((item.latitude + 90) / lat_step)
        x = math.floor((item.longitude + 180) / lon_step) % lon_bins
        furthest_latitude = min(89.9, abs(item.latitude) + lat_step)
        lon_radius = eps_km / (111.2 * max(0.001, math.cos(math.radians(furthest_latitude))))
        x_radius = math.ceil(lon_radius / lon_step) + 1
        candidates = (
            candidate
            for yi in range(y - 1, y + 2)
            for xi in range(x - x_radius, x + x_radius + 1)
            for candidate in buckets.get((yi, xi % lon_bins), ())
        )
        return sorted(
            candidate
            for candidate in candidates
            if abs((ordered[candidate].acquired_at - item.acquired_at).total_seconds())
            <= max_seconds
            and haversine_km(
                (item.longitude, item.latitude),
                (ordered[candidate].longitude, ordered[candidate].latitude),
            )
            <= eps_km
        )

    labels = [-1] * len(ordered)
    visited = [False] * len(ordered)
    cluster_id = 0
    for index in range(len(ordered)):
        if visited[index]:
            continue
        visited[index] = True
        adjacent = neighbors(index)
        if len(adjacent) < min_samples:
            continue
        labels[index] = cluster_id
        queue = deque(adjacent)
        queued = set(adjacent)
        while queue:
            candidate = queue.popleft()
            if not visited[candidate]:
                visited[candidate] = True
                connected = neighbors(candidate)
                if len(connected) >= min_samples:
                    for neighbor in connected:
                        if neighbor not in queued:
                            queue.append(neighbor)
                            queued.add(neighbor)
            if labels[candidate] == -1:
                labels[candidate] = cluster_id
        cluster_id += 1
    groups: dict[int, list[Observation]] = defaultdict(list)
    for item, label in zip(ordered, labels, strict=True):
        if label >= 0:
            groups[label].append(item)
    incidents = tuple(
        sorted((_summarize(group) for group in groups.values()), key=lambda item: item.incident_id)
    )
    noise_ids = tuple(
        sorted(
            item.observation_id for item, label in zip(ordered, labels, strict=True) if label < 0
        )
    )
    return ClusterResult(incidents, noise_ids)
