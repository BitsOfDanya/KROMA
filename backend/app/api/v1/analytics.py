from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.repositories.base import FireDataRepository
from app.repositories.provider import get_repository
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    repository: Annotated[FireDataRepository, Depends(get_repository)],
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    region: Annotated[str | None, Query(max_length=64)] = None,
) -> AnalyticsSummary:
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="'from' must not exceed 'to'")
    return AnalyticsService(repository).summary(start, end, region)
