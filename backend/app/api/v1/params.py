from datetime import datetime
from typing import Annotated, get_args

from fastapi import HTTPException, Query

from app.models.context import RiskObjectKind
from app.models.geometry import BBox
from app.models.incident import IncidentStatus, Severity
from app.models.observation import ObservationClass

BBOX_DESCRIPTION = "minLon,minLat,maxLon,maxLat in WGS84 (EPSG:4326)"


def _csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _validated(value: str | None, allowed: tuple[str, ...], name: str) -> tuple[str, ...] | None:
    items = _csv(value)
    if items is None:
        return None
    invalid = [item for item in items if item not in allowed]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported {name}: {', '.join(invalid)}")
    return tuple(items)


def parse_bbox(
    bbox: Annotated[str | None, Query(description=BBOX_DESCRIPTION)] = None,
) -> BBox | None:
    if bbox is None:
        return None
    try:
        values = tuple(float(part) for part in bbox.split(","))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="bbox must contain four numbers") from error
    if len(values) != 4:
        raise HTTPException(status_code=422, detail="bbox must contain four numbers")
    min_lon, min_lat, max_lon, max_lat = values
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise HTTPException(status_code=422, detail="bbox is outside WGS84 bounds or inverted")
    return (min_lon, min_lat, max_lon, max_lat)


def parse_statuses(
    status: Annotated[str | None, Query(description="Comma-separated incident statuses")] = None,
) -> tuple[IncidentStatus, ...] | None:
    return _validated(status, get_args(IncidentStatus), "status")


def parse_severities(
    severity: Annotated[str | None, Query(description="Comma-separated severities")] = None,
) -> tuple[Severity, ...] | None:
    return _validated(severity, get_args(Severity), "severity")


def parse_classifications(
    classification: Annotated[
        str | None, Query(description="Comma-separated observation classes")
    ] = None,
) -> tuple[ObservationClass, ...] | None:
    return _validated(classification, get_args(ObservationClass), "classification")


def parse_risk_kinds(
    kind: Annotated[str | None, Query(description="Comma-separated risk object kinds")] = None,
) -> tuple[RiskObjectKind, ...] | None:
    return _validated(kind, get_args(RiskObjectKind), "kind")


def parse_range(
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> tuple[datetime | None, datetime | None]:
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="'from' must not exceed 'to'")
    return start, end
