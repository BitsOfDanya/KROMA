from dataclasses import dataclass
from datetime import datetime, timedelta

from kroma_geo.measure import (
    bbox_intersects,
    bbox_of,
    distance_to_line_km,
    haversine_km,
    point_in_ring,
)

from app.models.context import RiskObject
from app.models.geometry import BBox, PointGeometry, PolygonGeometry, Position, Ring
from app.models.incident import (
    ForecastLevel,
    ForecastZone,
    Incident,
    IncidentStatus,
    NearestSettlement,
    PerimeterState,
    Severity,
)
from app.repositories.base import FireDataRepository
from app.schemas.incidents import (
    ForecastSummary,
    IncidentCounts,
    IncidentDetail,
    IncidentList,
    IncidentSummary,
    IncidentTimeline,
    PerimeterStateSummary,
    PerimeterSummary,
    RiskExposure,
    SortField,
)
from app.services.errors import NotFoundError

ACTIVE_STATUSES: tuple[IncidentStatus, ...] = ("suspected", "confirmed", "monitoring")
EXPOSURE_RADIUS_KM = 60
NEW_WINDOW = timedelta(hours=24)


def severity_for(priority: int) -> Severity:
    if priority >= 85:
        return "critical"
    if priority >= 65:
        return "high"
    if priority >= 40:
        return "medium"
    return "low"


@dataclass(frozen=True)
class IncidentFilter:
    statuses: tuple[IncidentStatus, ...] | None = None
    severities: tuple[Severity, ...] | None = None
    priority_min: int | None = None
    region_id: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    bbox: BBox | None = None
    query: str | None = None
    sort: SortField = "priority"
    descending: bool = True


def _distance_to_geometry(ring: Ring, item: RiskObject) -> float:
    geometry = item.geometry
    if isinstance(geometry, PointGeometry):
        if point_in_ring(geometry.coordinates, ring):
            return 0.0
        return distance_to_line_km(geometry.coordinates, ring)
    if isinstance(geometry, PolygonGeometry):
        outer = geometry.coordinates[0]
        if any(point_in_ring(vertex, outer) for vertex in ring):
            return 0.0
        return min(distance_to_line_km(vertex, ring) for vertex in outer[::2])
    return min(distance_to_line_km(vertex, geometry.coordinates) for vertex in ring)


def _densify(line: list[Position], step_deg: float) -> list[Position]:
    points: list[Position] = []
    for (lon1, lat1), (lon2, lat2) in zip(line, line[1:], strict=False):
        steps = max(1, int(max(abs(lon2 - lon1), abs(lat2 - lat1)) / step_deg))
        points.extend(
            (lon1 + (lon2 - lon1) * index / steps, lat1 + (lat2 - lat1) * index / steps)
            for index in range(steps)
        )
    points.append(line[-1])
    return points


def _forecast_level(item: RiskObject, zones: list[ForecastZone]) -> ForecastLevel | None:
    geometry = item.geometry
    if isinstance(geometry, PointGeometry):
        vertices = [geometry.coordinates]
    elif isinstance(geometry, PolygonGeometry):
        vertices = geometry.coordinates[0]
    else:
        vertices = _densify(geometry.coordinates, 0.02)
    for zone in sorted(zones, key=lambda value: value.level):
        ring = zone.geometry.coordinates[0]
        if any(point_in_ring(vertex, ring) for vertex in vertices):
            return zone.level
    return None


class IncidentService:
    def __init__(self, repository: FireDataRepository) -> None:
        self.repository = repository

    def _current_perimeter(self, incident_id: str) -> PerimeterState | None:
        states = self.repository.perimeters(incident_id)
        return states[-1] if states else None

    def _nearest_settlement(self, ring: Ring, bbox: BBox) -> NearestSettlement | None:
        search = (bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2)
        candidates = self.repository.risk_objects(search, ("settlement",))
        if not candidates:
            return None
        best = min(candidates, key=lambda item: _distance_to_geometry(ring, item))
        return NearestSettlement(
            name=best.name, distance_km=round(_distance_to_geometry(ring, best), 1)
        )

    def summarize(self, incident: Incident) -> IncidentSummary:
        latest = incident.snapshots[-1]
        perimeter = self._current_perimeter(incident.id)
        ring = perimeter.perimeter.coordinates[0] if perimeter else [incident.centroid]
        bbox = bbox_of(ring)
        reference = self.repository.reference_time()
        return IncidentSummary(
            id=incident.id,
            status=incident.status,
            severity=severity_for(latest.priority),
            region_id=incident.region_id,
            region=incident.region,
            district=incident.district,
            centroid=incident.centroid,
            bbox=bbox,
            first_detected_at=incident.first_detected_at,
            confirmed_at=incident.confirmed_at,
            updated_at=incident.updated_at,
            is_new=reference - incident.first_detected_at <= NEW_WINDOW,
            confidence=latest.confidence,
            threat=latest.threat,
            priority=latest.priority,
            area_ha=latest.area_ha,
            frp_mw=latest.frp_mw,
            observation_count=latest.observation_count,
            nearest_settlement=self._nearest_settlement(ring, bbox),
            spread=incident.spread,
            snapshots=incident.snapshots,
        )

    def counts(self, summaries: list[IncidentSummary]) -> IncidentCounts:
        active = [item for item in summaries if item.status in ACTIVE_STATUSES]
        return IncidentCounts(
            active=len(active),
            critical=sum(1 for item in active if item.severity == "critical"),
            new_24h=sum(1 for item in active if item.is_new),
            confirmed=sum(1 for item in active if item.status == "confirmed"),
            suspected=sum(1 for item in active if item.status == "suspected"),
            monitoring=sum(1 for item in active if item.status == "monitoring"),
        )

    def all_summaries(self) -> list[IncidentSummary]:
        return [self.summarize(incident) for incident in self.repository.incidents()]

    def list(self, filters: IncidentFilter) -> IncidentList:
        summaries = self.all_summaries()
        items = [item for item in summaries if self._matches(item, filters)]
        items.sort(key=lambda item: getattr(item, filters.sort), reverse=filters.descending)
        return IncidentList(
            items=items,
            total=len(items),
            counts=self.counts(summaries),
            generated_at=self.repository.reference_time(),
        )

    def _matches(self, item: IncidentSummary, filters: IncidentFilter) -> bool:
        if filters.statuses and item.status not in filters.statuses:
            return False
        if filters.severities and item.severity not in filters.severities:
            return False
        if filters.priority_min is not None and item.priority < filters.priority_min:
            return False
        if filters.region_id and item.region_id != filters.region_id:
            return False
        if filters.start and item.updated_at < filters.start:
            return False
        if filters.end and item.first_detected_at > filters.end:
            return False
        if filters.bbox and not bbox_intersects(item.bbox, filters.bbox):
            return False
        if filters.query:
            needle = filters.query.casefold()
            haystack = " ".join(
                [
                    item.id,
                    item.district,
                    item.region,
                    item.nearest_settlement.name if item.nearest_settlement else "",
                ]
            ).casefold()
            if needle not in haystack:
                return False
        return True

    def get(self, incident_id: str) -> Incident:
        incident = self.repository.incident(incident_id)
        if incident is None:
            raise NotFoundError("Incident", incident_id)
        return incident

    def detail(self, incident_id: str) -> IncidentDetail:
        incident = self.get(incident_id)
        summary = self.summarize(incident)
        perimeter = self._current_perimeter(incident.id)
        zones = self.repository.forecasts(incident.id)
        exposures: list[RiskExposure] = []
        perimeter_summary = None
        if perimeter:
            ring = perimeter.perimeter.coordinates[0]
            bbox = summary.bbox
            search = (bbox[0] - 1.5, bbox[1] - 0.8, bbox[2] + 1.5, bbox[3] + 0.8)
            for item in self.repository.risk_objects(search):
                distance = _distance_to_geometry(ring, item)
                if distance > EXPOSURE_RADIUS_KM:
                    continue
                exposures.append(
                    RiskExposure(
                        object_id=item.id,
                        kind=item.kind,
                        name=item.name,
                        subtitle=item.subtitle,
                        population=item.population,
                        distance_km=round(distance, 1),
                        forecast_level=_forecast_level(item, zones),
                    )
                )
            exposures.sort(key=lambda value: value.distance_km)
            front = perimeter.active_front.coordinates
            perimeter_summary = PerimeterSummary(
                observed_at=perimeter.observed_at,
                source=perimeter.source,
                area_ha=perimeter.area_ha,
                front_length_km=round(
                    sum(haversine_km(a, b) for a, b in zip(front, front[1:], strict=False)), 1
                ),
            )
        reference = self.repository.reference_time()
        next_passes = [
            item
            for item in self.repository.satellite_passes(incident.id)
            if item.overpass_at > reference
        ]
        return IncidentDetail(
            **summary.model_dump(),
            landcover=incident.landcover,
            ignition_point=incident.ignition_point,
            evidence=incident.evidence,
            exposures=exposures[:8],
            next_passes=next_passes[:8],
            perimeter=perimeter_summary,
            forecast=[
                ForecastSummary(
                    level=zone.level,
                    area_ha=zone.area_ha,
                    horizon_hours=zone.horizon_hours,
                    issued_at=zone.issued_at,
                )
                for zone in zones
            ],
            burn_scar_id=incident.burn_scar_id,
        )

    def timeline(self, incident_id: str) -> IncidentTimeline:
        incident = self.get(incident_id)
        return IncidentTimeline(
            incident_id=incident.id,
            events=self.repository.timeline(incident.id, None, None),
            snapshots=incident.snapshots,
            perimeters=[
                PerimeterStateSummary(
                    observed_at=state.observed_at,
                    valid_until=state.valid_until,
                    area_ha=state.area_ha,
                    source=state.source,
                )
                for state in self.repository.perimeters(incident.id)
            ],
            passes=self.repository.satellite_passes(incident.id),
        )
