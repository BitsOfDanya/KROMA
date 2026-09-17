from datetime import date, datetime
from typing import Literal

from app.models.geometry import BBox, PolygonGeometry, Position
from pydantic import BaseModel

BurnSeverity = Literal["low", "moderate", "high"]
AssessmentStatus = Literal["final", "preliminary"]


class SeverityZone(BaseModel):
    severity: BurnSeverity
    area_ha: float
    geometry: PolygonGeometry


class ImageryScene(BaseModel):
    satellite: str
    product: str
    acquired_on: date
    cloud_cover_pct: int
    scene_id: str


class BurnScar(BaseModel):
    id: str
    incident_id: str | None
    name: str
    region_id: str
    region: str
    district: str
    centroid: Position
    bbox: BBox
    fire_started_on: date
    fire_ended_on: date | None
    assessed_at: datetime
    assessment: AssessmentStatus
    landcover: str
    area_ha: float
    dnbr_mean: float
    geometry: PolygonGeometry
    zones: list[SeverityZone]
    before: ImageryScene
    after: ImageryScene
