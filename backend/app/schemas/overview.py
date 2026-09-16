from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.context import Region
from app.schemas.incidents import IncidentCounts


class Overview(BaseModel):
    generated_at: datetime
    reference_time: datetime
    data_source: Literal["demo"]
    regions: list[Region]
    default_region_id: str
    counts: IncidentCounts
    observations_24h: int
    raw_detections_7d: int
    last_observation_at: datetime | None
    top_incident_id: str | None
