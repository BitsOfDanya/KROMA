from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.geometry import BBox, LineGeometry, PointGeometry, PolygonGeometry, Position

RiskObjectKind = Literal["settlement", "power_line", "road", "infrastructure", "protected_area"]


class RiskObject(BaseModel):
    id: str
    kind: RiskObjectKind
    name: str
    subtitle: str
    region_id: str
    population: int | None = None
    geometry: PointGeometry | LineGeometry | PolygonGeometry


class Region(BaseModel):
    id: str
    name: str
    short_name: str
    bbox: BBox
    center: Position
    zoom: float


class WindSample(BaseModel):
    location: Position
    from_deg: float
    speed_ms: float


class CloudField(BaseModel):
    id: str
    probability: int
    geometry: PolygonGeometry


class WeeklyStat(BaseModel):
    week_start: date
    region_id: str
    incidents: int
    burned_area_ha: float
    high_severity_ha: float
    mean_confirmation_minutes: float
