from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.params import (
    parse_bbox,
    parse_classifications,
    parse_range,
    parse_risk_kinds,
)
from app.models.context import RiskObjectKind
from app.models.geometry import BBox
from app.models.observation import ObservationClass
from app.repositories.base import FireDataRepository
from app.repositories.provider import get_repository
from app.schemas.geojson import FeatureCollection
from app.services.map_layers import MapLayerService

router = APIRouter(prefix="/map", tags=["map"])
Repository = Annotated[FireDataRepository, Depends(get_repository)]
BBoxParam = Annotated[BBox | None, Depends(parse_bbox)]
Zoom = Annotated[float | None, Query(ge=0, le=24)]


@router.get("/hotspots", response_model=FeatureCollection)
def hotspots(
    repository: Repository,
    bbox: BBoxParam,
    time_range: Annotated[tuple[datetime | None, datetime | None], Depends(parse_range)],
    classifications: Annotated[tuple[ObservationClass, ...] | None, Depends(parse_classifications)],
    zoom: Zoom = None,
) -> FeatureCollection:
    return MapLayerService(repository).hotspots_layer(
        bbox, zoom, time_range[0], time_range[1], classifications
    )


@router.get("/incidents", response_model=FeatureCollection)
def incidents(repository: Repository, bbox: BBoxParam, zoom: Zoom = None) -> FeatureCollection:
    return MapLayerService(repository).incidents_layer(bbox)


@router.get("/perimeters", response_model=FeatureCollection)
def perimeters(
    repository: Repository,
    bbox: BBoxParam,
    incident_id: Annotated[str | None, Query(max_length=32)] = None,
    zoom: Zoom = None,
) -> FeatureCollection:
    return MapLayerService(repository).perimeters_layer(bbox, incident_id)


@router.get("/burn-scars", response_model=FeatureCollection)
def burn_scars(repository: Repository, bbox: BBoxParam, zoom: Zoom = None) -> FeatureCollection:
    return MapLayerService(repository).burn_scars_layer(bbox)


@router.get("/risk-objects", response_model=FeatureCollection)
def risk_objects(
    repository: Repository,
    bbox: BBoxParam,
    kinds: Annotated[tuple[RiskObjectKind, ...] | None, Depends(parse_risk_kinds)],
    zoom: Zoom = None,
) -> FeatureCollection:
    return MapLayerService(repository).risk_objects_layer(bbox, kinds)


@router.get("/thermal-sources", response_model=FeatureCollection)
def thermal_sources(repository: Repository, bbox: BBoxParam) -> FeatureCollection:
    return MapLayerService(repository).thermal_sources_layer(bbox)


@router.get("/wind", response_model=FeatureCollection)
def wind(repository: Repository, bbox: BBoxParam) -> FeatureCollection:
    return MapLayerService(repository).wind_layer(bbox)


@router.get("/clouds", response_model=FeatureCollection)
def clouds(repository: Repository, bbox: BBoxParam) -> FeatureCollection:
    return MapLayerService(repository).clouds_layer(bbox)
