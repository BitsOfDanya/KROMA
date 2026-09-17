from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.geometry import Position

LiveHealth = Literal["live", "nrt", "stale", "offline"]


class LiveDetection(BaseModel):
    id: str
    source: str
    satellite: str
    instrument: Literal["VIIRS", "MODIS"]
    acquired_at: datetime
    location: Position
    frp_mw: float | None
    brightness_k: float
    source_confidence: Literal["l", "n", "h"]
    daynight: Literal["D", "N"]
    pixel_size_m: int


class LiveIncident(BaseModel):
    id: str
    status: Literal["suspected", "confirmed", "monitoring"]
    severity: Literal["critical", "high", "medium", "low"]
    priority: int
    centroid: Position
    bbox: tuple[float, float, float, float]
    first_detected_at: datetime
    updated_at: datetime
    detection_count: int
    frp_mw: float
    sources: tuple[str, ...]


class LiveStatus(BaseModel):
    mode: Literal["live"] = "live"
    source: str
    status: LiveHealth
    configured: bool
    last_fetch_at: datetime | None
    latest_observation_at: datetime | None
    next_refresh_at: datetime | None
    refresh_interval_seconds: int
    detection_count: int
    incident_count: int
    error: str | None
