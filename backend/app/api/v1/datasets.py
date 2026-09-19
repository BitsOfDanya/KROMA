from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.repositories.prepared import PreparedDatasetRepository, get_prepared_repository
from app.services.exports import shapefile_zip
from app.services.ml_service import get_ml_service
from app.services.prediction import (
    feature_collection,
    overlay_png,
    prediction_payload,
    raster_package,
    validation_geometry,
)
from app.services.train_dataset import Asset, get_train_dataset_service
from app.services.upload_decode import MAX_UPLOAD_BYTES, decode_upload

router = APIRouter(tags=["datasets"])

UPLOAD_LIMITATION = (
    "Финальная модель принимает пакет официального чипа (AF: VIIRS + AUX; BS: Sentinel-2 до/после, "
    "Sentinel-1, AUX), а не одиночный снимок. Выберите train-чип по ID или загрузите пакет через "
    "подготовленный набор."
)


class MlPredictBody(BaseModel):
    chip_id: str = Field(..., examples=["BS_tr_000001"])


def _predict(kind: str, chip_id: str) -> dict[str, Any]:
    try:
        return prediction_payload(kind, chip_id)
    except HTTPException as error:
        if error.status_code != 503:
            raise
        return {
            "chip_id": chip_id,
            "kind": kind,
            "status": "unavailable",
            "detail": str(error.detail),
            "model_version": "unavailable",
            "runtime_ms": None,
            "mask_available": False,
            "polygons": [],
            "thermopoints": [],
        }


@router.get("/datasets", summary="Catalogue of official and prepared datasets")
def list_datasets(
    repository: PreparedDatasetRepository = Depends(get_prepared_repository),
) -> dict[str, Any]:
    train = get_train_dataset_service().summary()
    prepared = [
        {
            "id": f"{item.manifest.dataset_id}@{item.manifest.dataset_version}",
            "dataset_id": item.manifest.dataset_id,
            "dataset_version": item.manifest.dataset_version,
            "name": item.manifest.name,
            "origin": item.manifest.origin,
            "available_from": item.manifest.available_from,
            "available_to": item.manifest.available_to,
        }
        for item in repository.list()
    ]
    return {
        "items": [
            {
                "id": "official_train",
                "label": train["label"],
                "origin": "official_train",
                "available": train["available"],
                "counts": train["counts"],
                "geo_referenced": True,
            },
            *[{**item, "label": "PREPARED", "geo_referenced": True} for item in prepared],
        ],
        "competition_test": {
            "served": False,
            "note": (
                "Официальный test анонимизирован: без координат и меток, на карте не показывается."
            ),
        },
    }


@router.get("/datasets/train")
def list_train_chips(
    kind: Literal["af", "bs"] | None = None,
    has_fire: bool | None = None,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    service = get_train_dataset_service()
    summary = service.summary()
    listing = service.list_chips(kind=kind, has_fire=has_fire, q=q, limit=limit, offset=offset)
    return {**summary, **listing}


@router.get("/datasets/train/{chip_id}")
def get_train_chip(chip_id: str) -> dict:
    return get_train_dataset_service().get_chip(chip_id)


@router.get("/datasets/train/{chip_id}/preview/{asset}")
def preview_train_asset(
    chip_id: str,
    asset: Asset,
    size: int = Query(512, ge=64, le=1024),
) -> Response:
    png = get_train_dataset_service().preview_png(chip_id, asset, size=size)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/datasets/train/{chip_id}/prediction")
def train_prediction(chip_id: str) -> dict[str, Any]:
    kind = get_train_dataset_service().get_chip(chip_id)["kind"]
    return _predict(kind, chip_id)


@router.get("/datasets/train/{chip_id}/overlay/{layer}")
def train_overlay(
    chip_id: str,
    layer: Literal["pred", "gt", "error", "probability"],
    size: int = Query(512, ge=64, le=1024),
) -> Response:
    kind = get_train_dataset_service().get_chip(chip_id)["kind"]
    return Response(
        content=overlay_png(kind, chip_id, layer, size=size),
        media_type="image/png",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/datasets/train/{chip_id}/export")
def train_export(
    chip_id: str,
    layer: Literal["pred", "gt"] = "pred",
    export_format: Literal["geojson", "shp"] = Query("geojson", alias="format"),
) -> Response:
    kind = get_train_dataset_service().get_chip(chip_id)["kind"]
    collection = feature_collection(kind, chip_id, layer)
    if not collection["features"]:
        raise HTTPException(status_code=404, detail="No features in this layer")
    name = f"kroma-{chip_id}-{layer}"
    if export_format == "shp":
        return Response(
            shapefile_zip(collection["features"], name),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}-shapefile.zip"'},
        )
    return Response(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{name}.geojson"'},
    )


@router.get("/models", summary="Final model versions, artifacts and validated metrics")
def models() -> dict[str, Any]:
    status = get_ml_service().status()
    return status


@router.get("/ml/status")
def ml_status() -> dict:
    return get_ml_service().status()


@router.post("/inference/af")
def inference_af(body: MlPredictBody) -> dict:
    return _predict("af", body.chip_id)


@router.post("/inference/bs")
def inference_bs(body: MlPredictBody) -> dict:
    return _predict("bs", body.chip_id)


@router.post("/inference/upload")
async def inference_upload(
    task: Literal["af", "bs"] = Form("af"),
    file: UploadFile = File(...),
) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    decoded = decode_upload(file.filename or "upload.bin", data)
    decoded.pop("array", None)
    status = get_ml_service().status()
    return {
        "task": task,
        "input": decoded,
        "status": "unavailable",
        "detail": UPLOAD_LIMITATION,
        "model_version": status[task]["model_version"] or "unavailable",
        "runtime_ms": 0.0,
        "mask_png_b64": None,
        "metrics": {},
    }


@router.get("/datasets/train/{chip_id}/rasters")
def train_rasters(chip_id: str) -> Response:
    return Response(
        raster_package(chip_id),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{chip_id}-rasters.npz"'},
    )


@router.get("/datasets/train/{chip_id}/geometry")
def train_geometry(chip_id: str, layer: Literal["gt", "pred", "error"] = "pred") -> dict:
    return validation_geometry(chip_id, layer)
