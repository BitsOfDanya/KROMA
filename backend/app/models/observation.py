from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.geometry import BBox, Position

ObservationClass = Literal["incident", "persistent_source", "unassigned"]
SourceConfidence = Literal["l", "n", "h"]
SensorKind = Literal["thermal", "optical"]


class Observation(BaseModel):
    id: str
    incident_id: str | None
    classification: ObservationClass
    source: str
    satellite: str
    instrument: str
    acquired_at: datetime
    location: Position
    frp_mw: float
    brightness_k: float
    source_confidence: SourceConfidence
    daynight: Literal["D", "N"]
    pixel_size_m: int


class ThermalSource(BaseModel):
    id: str
    name: str
    kind: Literal["gas_flare", "industrial", "urban_heat"]
    location: Position
    observation_count: int
    history_years: float
    first_seen_at: datetime
    last_seen_at: datetime
    mean_frp_mw: float


class SatellitePass(BaseModel):
    id: str
    incident_id: str
    satellite: str
    instrument: str
    kind: SensorKind
    resolution_m: int
    overpass_at: datetime
    cloud_probability: int | None
    coverage: BBox
