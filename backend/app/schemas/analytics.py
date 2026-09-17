from datetime import date

from pydantic import BaseModel

from app.schemas.burn_scars import BurnScarSummary


class AnalyticsTotals(BaseModel):
    incidents: int
    burned_area_ha: float
    high_severity_ha: float
    high_severity_share: float
    mean_confirmation_minutes: float


class WeeklyPoint(BaseModel):
    week_start: date
    incidents: int
    burned_area_ha: float
    high_severity_ha: float
    mean_confirmation_minutes: float


class RegionBreakdown(BaseModel):
    region_id: str
    name: str
    incidents: int
    burned_area_ha: float
    high_severity_ha: float


class AnalyticsSummary(BaseModel):
    start: date
    end: date
    region_id: str | None
    totals: AnalyticsTotals
    series: list[WeeklyPoint]
    regions: list[RegionBreakdown]
    largest_burn_scars: list[BurnScarSummary]
