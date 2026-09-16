from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.context import RiskObjectKind
from app.models.geometry import BBox, Position
from app.models.incident import (
    EvidenceItem,
    ForecastLevel,
    IncidentSnapshot,
    IncidentStatus,
    NearestSettlement,
    Severity,
    SpreadEstimate,
    TimelineEvent,
)
from app.models.observation import SatellitePass


class IncidentSummary(BaseModel):
    id: str
    status: IncidentStatus
    severity: Severity
    region_id: str
    region: str
    district: str
    centroid: Position
    bbox: BBox
    first_detected_at: datetime
    confirmed_at: datetime | None
    updated_at: datetime
    is_new: bool
    confidence: int
    threat: int
    priority: int
    area_ha: float
    frp_mw: float
    observation_count: int
    nearest_settlement: NearestSettlement | None
    spread: SpreadEstimate
    snapshots: list[IncidentSnapshot]


class IncidentCounts(BaseModel):
    active: int
    critical: int
    new_24h: int
    confirmed: int
    suspected: int
    monitoring: int


class IncidentList(BaseModel):
    items: list[IncidentSummary]
    total: int
    counts: IncidentCounts
    generated_at: datetime


class RiskExposure(BaseModel):
    object_id: str
    kind: RiskObjectKind
    name: str
    subtitle: str
    population: int | None
    distance_km: float
    forecast_level: ForecastLevel | None


class PerimeterSummary(BaseModel):
    observed_at: datetime
    source: str
    area_ha: float
    front_length_km: float


class ForecastSummary(BaseModel):
    level: ForecastLevel
    area_ha: float
    horizon_hours: int
    issued_at: datetime


class IncidentDetail(IncidentSummary):
    landcover: str
    ignition_point: Position
    evidence: list[EvidenceItem]
    exposures: list[RiskExposure]
    next_passes: list[SatellitePass]
    perimeter: PerimeterSummary | None
    forecast: list[ForecastSummary]
    burn_scar_id: str | None


class PerimeterStateSummary(BaseModel):
    observed_at: datetime
    valid_until: datetime | None
    area_ha: float
    source: str


class IncidentTimeline(BaseModel):
    incident_id: str
    events: list[TimelineEvent]
    snapshots: list[IncidentSnapshot]
    perimeters: list[PerimeterStateSummary]
    passes: list[SatellitePass]


class TimelineResponse(BaseModel):
    start: datetime
    end: datetime
    events: list[TimelineEvent]


SortField = Literal[
    "priority", "updated_at", "first_detected_at", "area_ha", "confidence", "threat"
]


class HistogramBin(BaseModel):
    start: datetime
    total: int
    incident: int


class ObservationHistogram(BaseModel):
    start: datetime
    end: datetime
    bin_minutes: int
    bins: list[HistogramBin]
