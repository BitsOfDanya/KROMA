from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.services.ml_service import get_ml_service
from app.services.train_dataset import Asset, get_train_dataset_service

router = APIRouter(tags=["datasets"])


class MlPredictBody(BaseModel):
    chip_id: str = Field(..., examples=["BS_tr_000001"])


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
def preview_train_asset(chip_id: str, asset: Asset, size: int = Query(512, ge=64, le=1024)) -> Response:
    png = get_train_dataset_service().preview_png(chip_id, asset, size=size)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/ml/status")
def ml_status() -> dict:
    return get_ml_service().status()


@router.post("/inference/af")
def inference_af(body: MlPredictBody) -> dict:
    result = get_ml_service().predict_af(body.chip_id)
    return {
        "chip_id": result.chip_id,
        "model_version": result.model_version,
        "runtime_ms": result.runtime_ms,
        "n_fire_px": result.n_fire_px,
        "confidence_mean": result.confidence_mean,
        "thermopoints": result.thermopoints,
        "mask_available": result.mask_available,
        "status": result.status,
        "detail": result.detail,
    }


@router.post("/inference/bs")
def inference_bs(body: MlPredictBody) -> dict:
    result = get_ml_service().predict_bs(body.chip_id)
    return {
        "chip_id": result.chip_id,
        "model_version": result.model_version,
        "runtime_ms": result.runtime_ms,
        "total_area_ha": result.total_area_ha,
        "area_low_ha": result.area_low_ha,
        "area_moderate_ha": result.area_moderate_ha,
        "area_high_ha": result.area_high_ha,
        "polygons": result.polygons,
        "mask_available": result.mask_available,
        "status": result.status,
        "detail": result.detail,
    }


@router.post("/inference/upload")
async def inference_upload(
    task: Literal["af", "bs"] = Form("af"),
    file: UploadFile = File(...),
) -> dict:
    data = await file.read()
    return get_ml_service().predict_upload(task, file.filename or "upload.bin", data)
