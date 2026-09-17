from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.geometry import LineGeometry, PolygonGeometry, Position

IncidentStatus = Literal["suspected", "confirmed", "monitoring", "localized"]
Severity = Literal["critical", "high", "medium", "low"]
EvidenceEffect = Literal["raises", "lowers"]
EvidenceStrength = Literal["strong", "moderate", "weak"]
ForecastLevel = Literal["p50", "p80", "p95"]
TimelineEventKind = Literal[
    "detected",
    "observation",
    "confirmed",
    "priority_changed",
    "perimeter_updated",
    "forecast_issued",
    "weather_updated",
    "status_changed",
]


class IncidentSnapshot(BaseModel):
    observed_at: datetime
    status: IncidentStatus
    confidence: int
    threat: int
    priority: int
    area_ha: float
    frp_mw: float
    observation_count: int


class EvidenceItem(BaseModel):
    code: str
    label: str
    detail: str
    effect: EvidenceEffect
    strength: EvidenceStrength


class SpreadEstimate(BaseModel):
    direction_deg: float
    speed_m_per_h: float
    wind_from_deg: float
    wind_speed_ms: float


class NearestSettlement(BaseModel):
    name: str
    distance_km: float


class Incident(BaseModel):
    id: str
    status: IncidentStatus
    region_id: str
    region: str
    district: str
    centroid: Position
    ignition_point: Position
    first_detected_at: datetime
    confirmed_at: datetime | None
    updated_at: datetime
    landcover: str
    spread: SpreadEstimate
    snapshots: list[IncidentSnapshot]
    evidence: list[EvidenceItem]
    burn_scar_id: str | None = None


class PerimeterState(BaseModel):
    incident_id: str
    observed_at: datetime
    valid_until: datetime | None
    source: str
    area_ha: float
    perimeter: PolygonGeometry
    active_front: LineGeometry


class ForecastZone(BaseModel):
    id: str
    incident_id: str
    level: ForecastLevel
    issued_at: datetime
    horizon_hours: int
    area_ha: float
    geometry: PolygonGeometry


class TimelineEvent(BaseModel):
    id: str
    incident_id: str | None
    occurred_at: datetime
    kind: TimelineEventKind
    title: str
    detail: str
