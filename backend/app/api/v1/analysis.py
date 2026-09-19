from __future__ import annotations

import csv
import io
import json
import logging
import math
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.models.geometry import BBox
from app.repositories.prepared import PreparedDatasetRepository, get_prepared_repository
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResult,
    ApiErrorResponse,
    DatasetCatalogResponse,
)
from app.services.analysis import AnalysisService
from app.services.errors import ResultConflictError
from app.services.exports import shapefile_zip

router = APIRouter(prefix="/analysis", tags=["Spatial analysis"])
logger = logging.getLogger(__name__)

ERROR_RESPONSES = {
    404: {"model": ApiErrorResponse, "description": "Unknown dataset or immutable version"},
    409: {
        "model": ApiErrorResponse,
        "description": "The displayed result is no longer the requested result",
    },
    422: {
        "model": ApiErrorResponse,
        "description": "Invalid bbox, dates, format, or configured limit",
    },
    503: {
        "model": ApiErrorResponse,
        "description": "Dataset artifacts are unavailable or failed integrity checks",
    },
}


def _bbox(value: str) -> BBox:
    try:
        parts = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="bbox must contain four finite numbers"
        ) from error
    if len(parts) != 4 or not all(math.isfinite(item) for item in parts):
        raise HTTPException(status_code=422, detail="bbox must contain four finite numbers")
    min_lon, min_lat, max_lon, max_lat = parts
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise HTTPException(
            status_code=422,
            detail=(
                "bbox must be minLon,minLat,maxLon,maxLat in WGS84 with positive width and height"
            ),
        )
    return (min_lon, min_lat, max_lon, max_lat)


def analysis_request(
    dataset_id: Annotated[
        str,
        Query(description="Prepared dataset ID from the catalog", examples=["kroma-ci-demo"]),
    ],
    dataset_version: Annotated[
        str,
        Query(description="Required immutable dataset version", examples=["1.0.0"]),
    ],
    bbox: Annotated[
        str,
        Query(
            description=(
                "minLon,minLat,maxLon,maxLat in WGS84; antimeridian crossing is unsupported"
            ),
            examples=["99.03,58.03,99.13,58.13"],
        ),
    ],
    start: Annotated[
        date,
        Query(
            alias="from", description="First inclusive UTC calendar day", examples=["2024-08-10"]
        ),
    ],
    end: Annotated[
        date,
        Query(alias="to", description="Last inclusive UTC calendar day", examples=["2024-08-20"]),
    ],
) -> AnalysisRequest:
    try:
        return AnalysisRequest(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            bbox=_bbox(bbox),
            start=start,
            end=end,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _service(repository: PreparedDatasetRepository) -> AnalysisService:
    return AnalysisService(repository)


def _analyze(repository: PreparedDatasetRepository, request: AnalysisRequest) -> AnalysisResult:
    try:
        return _service(repository).analyze(request)
    except ValueError as error:
        logger.warning(
            "analysis_rejected dataset=%s version=%s from=%s to=%s error=%s",
            request.dataset_id,
            request.dataset_version,
            request.start,
            request.end,
            type(error).__name__,
        )
        raise HTTPException(status_code=422, detail=str(error)) from error


def _assert_result(result: AnalysisResult, expected_result_id: str) -> None:
    if result.result_id != expected_result_id:
        raise ResultConflictError(
            "expected_result_id does not match the current immutable calculation; "
            "run analysis again"
        )


def _safe_csv(value: object) -> object:
    if not isinstance(value, str):
        return value
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


def _filename(result: AnalysisResult, extension: str) -> str:
    request = result.request
    return (
        f"kroma-{request.dataset_id}-{request.start.isoformat()}-"
        f"{request.end.isoformat()}-{result.result_id[3:11]}.{extension}"
    )


@router.get(
    "/datasets",
    response_model=DatasetCatalogResponse,
    summary="List immutable prepared datasets",
    description=(
        "Returns coverage, date range, provenance and a guaranteed example query "
        "for each verified manifest."
    ),
)
def datasets(
    repository: Annotated[PreparedDatasetRepository, Depends(get_prepared_repository)],
) -> DatasetCatalogResponse:
    return _service(repository).catalog()


@router.get(
    "/readiness",
    summary="Check prepared-analysis readiness",
    description=(
        "Unlike /health, verifies that at least one manifest and all of its artifacts "
        "passed integrity checks."
    ),
)
def readiness(
    repository: Annotated[PreparedDatasetRepository, Depends(get_prepared_repository)],
) -> dict[str, object]:
    body = _service(repository).readiness()
    if body["status"] != "ready":
        raise HTTPException(status_code=503, detail=body)
    return body


@router.get(
    "",
    response_model=AnalysisResult,
    responses=ERROR_RESPONSES,
    summary="Analyze one area and inclusive UTC period",
    description=(
        "Returns hotspots, clipped non-overlapping burn-severity zones, summary, source-specific "
        "coverage and provenance under one deterministic result_id. Burn scars are selected by "
        "after-acquisition date, not fire start date."
    ),
)
def analyze(
    request: Annotated[AnalysisRequest, Depends(analysis_request)],
    repository: Annotated[PreparedDatasetRepository, Depends(get_prepared_repository)],
) -> AnalysisResult:
    return _analyze(repository, request)


@router.get(
    "/export/contours",
    responses=ERROR_RESPONSES,
    summary="Download the displayed burn zones as GeoJSON",
)
def export_contours(
    request: Annotated[AnalysisRequest, Depends(analysis_request)],
    repository: Annotated[PreparedDatasetRepository, Depends(get_prepared_repository)],
    expected_result_id: Annotated[
        str, Query(description="result_id returned by the analysis currently shown to the user")
    ],
) -> Response:
    result = _analyze(repository, request)
    _assert_result(result, expected_result_id)
    content = result.burn_zones.model_dump(mode="json")
    content.update(
        {
            "result_id": result.result_id,
            "request": result.request.model_dump(mode="json", by_alias=True),
            "provenance": result.provenance.model_dump(mode="json"),
            "calculation": result.calculation.model_dump(mode="json"),
        }
    )
    return Response(
        json.dumps(content, ensure_ascii=False, separators=(",", ":")),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{_filename(result, "geojson")}"'},
    )


@router.get(
    "/export/shapefile",
    responses=ERROR_RESPONSES,
    summary="Download the displayed burn zones as an ESRI Shapefile ZIP (WGS84)",
)
def export_shapefile(
    request: Annotated[AnalysisRequest, Depends(analysis_request)],
    repository: Annotated[PreparedDatasetRepository, Depends(get_prepared_repository)],
    expected_result_id: Annotated[
        str, Query(description="result_id returned by the analysis currently shown to the user")
    ],
) -> Response:
    result = _analyze(repository, request)
    _assert_result(result, expected_result_id)
    features = result.burn_zones.model_dump(mode="json")["features"]
    if not features:
        raise HTTPException(status_code=404, detail="No burn zones in the requested area")
    return Response(
        shapefile_zip(features, _filename(result, "shp")[:-4]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_filename(result, "zip")}"'},
    )


@router.get(
    "/export/report",
    responses=ERROR_RESPONSES,
    summary="Download the displayed report as CSV or JSON",
)
def export_report(
    request: Annotated[AnalysisRequest, Depends(analysis_request)],
    repository: Annotated[PreparedDatasetRepository, Depends(get_prepared_repository)],
    expected_result_id: Annotated[
        str, Query(description="result_id returned by the analysis currently shown to the user")
    ],
    report_format: Annotated[
        Literal["csv", "json"],
        Query(alias="format", description="Machine-readable report format"),
    ] = "csv",
) -> Response:
    result = _analyze(repository, request)
    _assert_result(result, expected_result_id)
    if report_format == "json":
        return Response(
            result.model_dump_json(by_alias=True),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{_filename(result, "json")}"'},
        )

    output = io.StringIO(newline="")
    fieldnames = [
        "row_type",
        "class_id",
        "label",
        "area_ha",
        "share",
        "hotspot_count",
        "burn_scar_count",
        "zone_count",
        "summary_status",
        "coverage_status",
        "dataset_id",
        "dataset_version",
        "processing_version",
        "origin",
        "bbox",
        "from",
        "to",
        "timezone",
        "temporal_rule",
        "scene_ids",
        "area_crs",
        "area_method",
        "warnings",
        "result_id",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    common = {
        "hotspot_count": result.summary.hotspot_count,
        "burn_scar_count": result.summary.burn_scar_count,
        "zone_count": result.summary.zone_count,
        "summary_status": result.summary.status,
        "coverage_status": result.coverage.status,
        "dataset_id": result.request.dataset_id,
        "dataset_version": result.request.dataset_version,
        "processing_version": result.provenance.processing_version,
        "origin": result.provenance.origin,
        "bbox": ",".join(format(value, ".15g") for value in result.request.bbox),
        "from": result.request.start.isoformat(),
        "to": result.request.end.isoformat(),
        "timezone": "UTC",
        "temporal_rule": result.provenance.temporal_rule,
        "scene_ids": "|".join(result.provenance.scene_ids),
        "area_crs": result.calculation.area_crs,
        "area_method": result.calculation.area_method,
        "warnings": "|".join(item.code for item in result.warnings),
        "result_id": result.result_id,
    }
    writer.writerow(
        {
            key: _safe_csv(value)
            for key, value in {
                **common,
                "row_type": "total",
                "class_id": "",
                "label": "Вся выгоревшая площадь",
                "area_ha": result.summary.total_burned_area_ha
                if result.summary.total_burned_area_ha is not None
                else "",
                "share": 1 if result.summary.total_burned_area_ha else "",
            }.items()
        }
    )
    for item in result.summary.severity:
        writer.writerow(
            {
                key: _safe_csv(value)
                for key, value in {
                    **common,
                    "row_type": "severity",
                    "class_id": item.class_id,
                    "label": item.label,
                    "area_ha": item.area_ha if item.area_ha is not None else "",
                    "share": item.share if item.share is not None else "",
                }.items()
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename(result, "csv")}"'},
    )
