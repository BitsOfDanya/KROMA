from datetime import UTC, datetime

from app.demo.dataset import DemoDataset, build_dataset
from app.models.burn_scar import BurnScar
from app.models.context import (
    CloudField,
    Region,
    RiskObject,
    RiskObjectKind,
    WeeklyStat,
    WindSample,
)
from app.models.geometry import BBox, LineGeometry, PointGeometry, PolygonGeometry
from app.models.incident import ForecastZone, Incident, PerimeterState, TimelineEvent
from app.models.observation import Observation, SatellitePass, ThermalSource
from app.repositories.base import ObservationQuery
from kroma_geo.measure import bbox_intersects, bbox_of, point_in_bbox


def _geometry_bbox(geometry: PointGeometry | LineGeometry | PolygonGeometry) -> BBox:
    if isinstance(geometry, PointGeometry):
        lon, lat = geometry.coordinates
        return (lon, lat, lon, lat)
    if isinstance(geometry, LineGeometry):
        return bbox_of(geometry.coordinates)
    return bbox_of(geometry.coordinates[0])


class DemoFireRepository:
    def __init__(self, anchor: datetime | None = None) -> None:
        self._data: DemoDataset = build_dataset(anchor or datetime.now(UTC))
        self._incidents = {incident.id: incident for incident in self._data.incidents}
        self._burn_scars = {scar.id: scar for scar in self._data.burn_scars}
        self._risk_bboxes = {
            item.id: _geometry_bbox(item.geometry) for item in self._data.risk_objects
        }
        self._cloud_bboxes = {
            item.id: bbox_of(item.geometry.coordinates[0]) for item in self._data.clouds
        }

    def reference_time(self) -> datetime:
        return self._data.anchor

    def regions(self) -> list[Region]:
        return list(self._data.regions)

    def incidents(self) -> list[Incident]:
        return list(self._data.incidents)

    def incident(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id.upper())

    def perimeters(self, incident_id: str | None = None) -> list[PerimeterState]:
        return [
            item
            for item in self._data.perimeters
            if incident_id is None or item.incident_id == incident_id
        ]

    def forecasts(self, incident_id: str) -> list[ForecastZone]:
        return [item for item in self._data.forecasts if item.incident_id == incident_id]

    def observations(self, query: ObservationQuery) -> list[Observation]:
        return [
            item
            for item in self._data.observations
            if (query.incident_id is None or item.incident_id == query.incident_id)
            and (query.bbox is None or point_in_bbox(item.location, query.bbox))
            and (query.start is None or item.acquired_at >= query.start)
            and (query.end is None or item.acquired_at <= query.end)
            and (query.classifications is None or item.classification in query.classifications)
        ]

    def timeline(
        self, incident_id: str | None, start: datetime | None, end: datetime | None
    ) -> list[TimelineEvent]:
        return [
            item
            for item in self._data.timeline
            if (incident_id is None or item.incident_id == incident_id)
            and (start is None or item.occurred_at >= start)
            and (end is None or item.occurred_at <= end)
        ]

    def satellite_passes(self, incident_id: str) -> list[SatellitePass]:
        return [item for item in self._data.passes if item.incident_id == incident_id]

    def thermal_sources(self, bbox: BBox | None) -> list[ThermalSource]:
        return [
            item
            for item in self._data.thermal_sources
            if bbox is None or point_in_bbox(item.location, bbox)
        ]

    def risk_objects(
        self, bbox: BBox | None, kinds: tuple[RiskObjectKind, ...] | None = None
    ) -> list[RiskObject]:
        return [
            item
            for item in self._data.risk_objects
            if (kinds is None or item.kind in kinds)
            and (bbox is None or bbox_intersects(self._risk_bboxes[item.id], bbox))
        ]

    def burn_scars(self) -> list[BurnScar]:
        return list(self._data.burn_scars)

    def burn_scar(self, burn_scar_id: str) -> BurnScar | None:
        return self._burn_scars.get(burn_scar_id.upper())

    def wind(self, bbox: BBox | None) -> list[WindSample]:
        return [
            item for item in self._data.wind if bbox is None or point_in_bbox(item.location, bbox)
        ]

    def clouds(self, bbox: BBox | None) -> list[CloudField]:
        return [
            item
            for item in self._data.clouds
            if bbox is None or bbox_intersects(self._cloud_bboxes[item.id], bbox)
        ]

    def weekly_stats(self) -> list[WeeklyStat]:
        return list(self._data.weekly_stats)
