from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.params import parse_bbox, parse_range
from app.models.geometry import BBox
from app.repositories.base import FireDataRepository, ObservationQuery
from app.repositories.provider import get_repository
from app.schemas.incidents import HistogramBin, ObservationHistogram, TimelineResponse
from app.schemas.overview import Overview
from app.services.overview import OverviewService

router = APIRouter(tags=["overview"])
Repository = Annotated[FireDataRepository, Depends(get_repository)]


@router.get("/overview", response_model=Overview)
def overview(repository: Repository) -> Overview:
    return OverviewService(repository).overview()


@router.get("/timeline", response_model=TimelineResponse)
def timeline(
    repository: Repository,
    time_range: Annotated[tuple[datetime | None, datetime | None], Depends(parse_range)],
) -> TimelineResponse:
    reference = repository.reference_time()
    start = time_range[0] or min(
        (item.occurred_at for item in repository.timeline(None, None, None)), default=reference
    )
    end = time_range[1] or reference
    return TimelineResponse(start=start, end=end, events=repository.timeline(None, start, end))


@router.get("/observations/histogram", response_model=ObservationHistogram)
def observation_histogram(
    repository: Repository,
    time_range: Annotated[tuple[datetime | None, datetime | None], Depends(parse_range)],
    bbox: Annotated[BBox | None, Depends(parse_bbox)],
    bins: Annotated[int, Query(ge=4, le=400)] = 96,
) -> ObservationHistogram:
    end = time_range[1] or repository.reference_time()
    start = time_range[0] or end - timedelta(days=1)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    step = (end - start) / bins
    totals = [0] * bins
    incident = [0] * bins
    observations = repository.observations(ObservationQuery(bbox=bbox, start=start, end=end))
    for item in observations:
        index = min(bins - 1, int((item.acquired_at - start) / step))
        totals[index] += 1
        if item.classification == "incident":
            incident[index] += 1
    return ObservationHistogram(
        start=start,
        end=end,
        bin_minutes=max(1, round(step.total_seconds() / 60)),
        bins=[
            HistogramBin(start=start + step * index, total=totals[index], incident=incident[index])
            for index in range(bins)
        ],
    )
