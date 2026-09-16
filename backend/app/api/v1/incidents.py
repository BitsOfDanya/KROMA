from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.params import parse_bbox, parse_range, parse_severities, parse_statuses
from app.models.geometry import BBox
from app.models.incident import IncidentStatus, Severity
from app.repositories.base import FireDataRepository
from app.repositories.provider import get_repository
from app.schemas.geojson import FeatureCollection
from app.schemas.incidents import IncidentDetail, IncidentList, IncidentTimeline, SortField
from app.services.incidents import IncidentFilter, IncidentService
from app.services.map_layers import MapLayerService

router = APIRouter(prefix="/incidents", tags=["incidents"])
Repository = Annotated[FireDataRepository, Depends(get_repository)]


@router.get("", response_model=IncidentList)
def list_incidents(
    repository: Repository,
    statuses: Annotated[tuple[IncidentStatus, ...] | None, Depends(parse_statuses)],
    severities: Annotated[tuple[Severity, ...] | None, Depends(parse_severities)],
    bbox: Annotated[BBox | None, Depends(parse_bbox)],
    time_range: Annotated[tuple[datetime | None, datetime | None], Depends(parse_range)],
    priority_min: Annotated[int | None, Query(ge=0, le=100)] = None,
    region: Annotated[str | None, Query(max_length=64)] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    sort: SortField = "priority",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> IncidentList:
    return IncidentService(repository).list(
        IncidentFilter(
            statuses=statuses,
            severities=severities,
            priority_min=priority_min,
            region_id=region,
            start=time_range[0],
            end=time_range[1],
            bbox=bbox,
            query=q,
            sort=sort,
            descending=order == "desc",
        )
    )


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: str, repository: Repository) -> IncidentDetail:
    return IncidentService(repository).detail(incident_id)


@router.get("/{incident_id}/observations", response_model=FeatureCollection)
def get_incident_observations(incident_id: str, repository: Repository) -> FeatureCollection:
    return MapLayerService(repository).incident_observations(incident_id)


@router.get("/{incident_id}/timeline", response_model=IncidentTimeline)
def get_incident_timeline(incident_id: str, repository: Repository) -> IncidentTimeline:
    return IncidentService(repository).timeline(incident_id)


@router.get("/{incident_id}/forecast", response_model=FeatureCollection)
def get_incident_forecast(incident_id: str, repository: Repository) -> FeatureCollection:
    return MapLayerService(repository).forecast_layer(incident_id)
