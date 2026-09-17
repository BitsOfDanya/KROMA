from datetime import date, datetime

from pydantic import BaseModel

from app.models.burn_scar import AssessmentStatus
from app.models.geometry import BBox, Position


class SeverityBreakdown(BaseModel):
    low_ha: float
    moderate_ha: float
    high_ha: float


class BurnScarSummary(BaseModel):
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
    area_ha: float
    dnbr_mean: float
    severity: SeverityBreakdown


class BurnScarList(BaseModel):
    items: list[BurnScarSummary]
    total: int
