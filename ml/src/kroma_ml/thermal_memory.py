import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from kroma_geo.measure import EARTH_RADIUS_KM, haversine_km

from kroma_ml.incidents import Observation

Cell = tuple[int, int]


@dataclass(frozen=True)
class EqualAreaGrid:
    cell_km: float = 2.0

    def __post_init__(self) -> None:
        if self.cell_km <= 0:
            raise ValueError("cell_km must be positive")

    @property
    def width(self) -> int:
        return math.ceil(2 * math.pi * EARTH_RADIUS_KM / self.cell_km)

    @property
    def height(self) -> int:
        return math.ceil(2 * EARTH_RADIUS_KM / self.cell_km)

    def cell(self, longitude: float, latitude: float) -> Cell:
        x = min(self.width - 1, math.floor(((longitude + 180) % 360) / 360 * self.width))
        y = min(
            self.height - 1,
            math.floor((math.sin(math.radians(latitude)) + 1) / 2 * self.height),
        )
        return x, y

    def nearby(self, longitude: float, latitude: float) -> tuple[Cell, ...]:
        x, y = self.cell(longitude, latitude)
        return tuple(
            ((x + dx) % self.width, y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if 0 <= y + dy < self.height
        )


@dataclass(frozen=True)
class ThermalProfile:
    historical_detection_count: int
    active_days: int
    active_months: int
    mean_frp_mw: float | None
    max_frp_mw: float | None
    night_ratio: float | None
    sensor_count: int
    coordinate_spread_km: float | None
    last_seen_before_event: datetime | None
    seasonal_detection_count: int
    thermal_novelty_score: float | None
    reason: str


class ThermalMemory:
    def __init__(self, observations: list[Observation], grid: EqualAreaGrid | None = None) -> None:
        self.grid = grid or EqualAreaGrid()
        self.by_cell: dict[Cell, list[Observation]] = defaultdict(list)
        self.earliest = min((item.acquired_at for item in observations), default=None)
        self.latest = max((item.acquired_at for item in observations), default=None)
        self.reference_cache: dict[tuple[str | None, int, datetime], list[int]] = {}
        for item in observations:
            cell = self.grid.cell(item.longitude, item.latitude)
            self.by_cell[cell].append(item)

    def _reference_counts(
        self, region: str | None, month: int, historical_from: datetime, event_at: datetime
    ) -> list[int]:
        cache_key = region, month, historical_from
        can_cache = (
            self.earliest is not None
            and self.earliest >= historical_from
            and self.latest < event_at
        )
        if can_cache and cache_key in self.reference_cache:
            return self.reference_cache[cache_key]
        counts = sorted(
            sum(
                historical_from <= item.acquired_at < event_at
                and item.acquired_at.month == month
                and (region is None or item.region == region)
                for neighbor in self.grid.nearby(items[0].longitude, items[0].latitude)
                for item in self.by_cell.get(neighbor, ())
            )
            for items in self.by_cell.values()
            if items
        )
        counts = [count for count in counts if count]
        if can_cache:
            self.reference_cache[cache_key] = counts
        return counts

    def profile(
        self,
        longitude: float,
        latitude: float,
        event_at: datetime,
        historical_from: datetime,
        region: str | None = None,
    ) -> ThermalProfile:
        if event_at.utcoffset() is None or historical_from.utcoffset() is None:
            raise ValueError("times must include timezone")
        if historical_from >= event_at:
            raise ValueError("historical_from must precede event_at")
        nearby = self.grid.nearby(longitude, latitude)
        history = [
            item
            for cell in nearby
            for item in self.by_cell.get(cell, ())
            if historical_from <= item.acquired_at < event_at
            and (region is None or item.region == region)
        ]
        seasonal = [item for item in history if item.acquired_at.month == event_at.month]
        frps = [item.frp_mw for item in history if item.frp_mw is not None]
        night = [item.daynight for item in history if item.daynight in {"D", "N"}]
        if not history:
            novelty = 1.0
            reason = "no historical detections in local grid neighborhood"
        else:
            reference = self._reference_counts(region, event_at.month, historical_from, event_at)
            seasonal_days = len({item.acquired_at.date() for item in seasonal})
            if reference:
                rank = sum(count <= len(seasonal) for count in reference) / len(reference)
                novelty = round(1 - rank, 3) if seasonal else 1.0
            else:
                novelty = None
            active_days = len({item.acquired_at.date() for item in history})
            reason = (
                f"{len(history)} detections on {active_days} days; "
                f"{len(seasonal)} in event month on {seasonal_days} days"
            )
        return ThermalProfile(
            historical_detection_count=len(history),
            active_days=len({item.acquired_at.date() for item in history}),
            active_months=len(
                {(item.acquired_at.year, item.acquired_at.month) for item in history}
            ),
            mean_frp_mw=sum(frps) / len(frps) if frps else None,
            max_frp_mw=max(frps) if frps else None,
            night_ratio=night.count("N") / len(night) if night else None,
            sensor_count=len({item.satellite for item in history}),
            coordinate_spread_km=(
                sum(
                    haversine_km((longitude, latitude), (item.longitude, item.latitude))
                    for item in history
                )
                / len(history)
                if history
                else None
            ),
            last_seen_before_event=max(item.acquired_at for item in history) if history else None,
            seasonal_detection_count=len(seasonal),
            thermal_novelty_score=novelty,
            reason=reason,
        )
