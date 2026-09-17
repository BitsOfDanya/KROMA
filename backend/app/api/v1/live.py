from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.params import parse_bbox
from app.live.models import LiveStatus
from app.live.service import LiveService, get_live_service
from app.models.geometry import BBox
from app.schemas.geojson import FeatureCollection

router = APIRouter(prefix="/live", tags=["live"])
Service = Annotated[LiveService, Depends(get_live_service)]
BBoxParam = Annotated[BBox | None, Depends(parse_bbox)]


@router.get("/status", response_model=LiveStatus)
def live_status(service: Service) -> LiveStatus:
    return service.status()


@router.get("/hotspots", response_model=FeatureCollection)
def live_hotspots(service: Service, bbox: BBoxParam) -> FeatureCollection:
    return service.hotspots(bbox)


@router.get("/incidents", response_model=FeatureCollection)
def live_incidents(service: Service, bbox: BBoxParam) -> FeatureCollection:
    return service.incidents(bbox)
