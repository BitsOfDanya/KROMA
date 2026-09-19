from __future__ import annotations

import io
import time
from typing import Any, Literal

import numpy as np
from fastapi import HTTPException
from kroma_geo.raster_vector import ChipGeoreference, class_features, pixel_area_ha, point_features
from PIL import Image

from app.services.ml_service import MlUnavailableError, get_ml_service
from app.services.train_dataset import get_train_dataset_service

Layer = Literal["pred", "gt", "error"]
SEVERITY = {1: "low", 2: "moderate", 3: "high"}
SOURCE_PRED = "official_train_in_sample_prediction"
SOURCE_GT = "official_train_ground_truth"
SCOPE = {
    "scope": "in_sample",
    "note": (
        "Финальная модель обучена на всех official train чипах, поэтому качество на них "
        "завышено. Оценка обобщения — только по OOF-метрикам в research/report.md."
    ),
}
COLORS = {
    "low": (232, 176, 88, 210),
    "moderate": (232, 120, 64, 225),
    "high": (220, 56, 48, 240),
    "fire": (220, 56, 48, 230),
    "tp": (66, 190, 120, 230),
    "fp": (220, 56, 48, 230),
    "fn": (72, 132, 232, 230),
    "wrong": (240, 190, 60, 230),
}


def _chip(chip_id: str) -> tuple[dict[str, Any], ChipGeoreference | None]:
    service = get_train_dataset_service()
    return service.get_chip(chip_id), service.georef(chip_id)


def af_metrics(mask: np.ndarray, gt: np.ndarray, valid: np.ndarray) -> dict[str, Any]:
    pred, truth = mask.astype(bool) & valid, gt.astype(bool) & valid
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "gt_fire_px": int(truth.sum()),
        "pred_fire_px": int(pred.sum()),
    }


def _iou(pred: np.ndarray, truth: np.ndarray) -> float | None:
    union = int((pred | truth).sum())
    return float((pred & truth).sum()) / union if union else None


def bs_metrics(mask: np.ndarray, gt: np.ndarray, valid: np.ndarray) -> dict[str, Any]:
    pred, truth = mask.astype(np.int64), gt.astype(np.int64)
    per_class = {SEVERITY[k]: _iou((pred == k) & valid, (truth == k) & valid) for k in (1, 2, 3)}
    present = [v for v in per_class.values() if v is not None]
    confusion = np.bincount(
        (truth[valid] * 4 + pred[valid]).astype(np.int64), minlength=16
    ).reshape(4, 4)
    return {
        "iou_burn": _iou((pred > 0) & valid, (truth > 0) & valid),
        "iou_by_severity": per_class,
        "miou_severity": float(np.mean(present)) if present else None,
        "confusion": confusion.tolist(),
        "gt_burn_px": int(((truth > 0) & valid).sum()),
        "pred_burn_px": int(((pred > 0) & valid).sum()),
    }


def _run(kind: str, chip_id: str) -> dict[str, Any]:
    try:
        return get_ml_service().run(kind, chip_id)
    except MlUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def prediction_payload(kind: str, chip_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    chip, georef = _chip(chip_id)
    if chip["kind"] != kind:
        raise HTTPException(status_code=422, detail=f"{chip_id} is a {chip['kind'].upper()} chip")
    result = _run(kind, chip_id)
    ml_ms = result["runtime_ms"]["total"] if kind == "bs" else result["runtime_ms"]
    t_geo = time.perf_counter()
    mask, gt, valid = result["mask"], result["gt_mask"], result["valid"]
    payload: dict[str, Any] = {
        "chip_id": chip_id,
        "kind": kind,
        "status": "ok",
        "detail": None,
        "model_version": result["model_version"],
        "prediction": SCOPE,
        "georeferenced": georef is not None,
        "gsd_m": georef.gsd_x if georef else chip.get("gsd_m"),
    }
    if kind == "af":
        payload["metrics"] = af_metrics(mask, gt, valid)
        payload["n_fire_px"] = result["fire_pixels"]
        proba = result["probability"]
        payload["confidence_mean"] = float(proba[mask.astype(bool)].mean()) if mask.any() else None
        payload["threshold"] = result["threshold"]
        payload["thermopoints"] = (
            point_features(
                mask,
                georef,
                scene_id=chip_id,
                model_version=result["model_version"],
                source=SOURCE_PRED,
                values=proba,
                limit=2000,
            )
            if georef
            else []
        )
        payload["polygons"] = []
        payload["area_ha"] = None
    else:
        payload["metrics"] = bs_metrics(mask, gt, valid)
        pixel_ha = pixel_area_ha(1, georef) if georef else 0.04
        areas = {
            name: round(float((mask == k).sum()) * pixel_ha, 2) for k, name in SEVERITY.items()
        }
        gt_areas = {
            name: round(float((gt == k).sum()) * pixel_ha, 2) for k, name in SEVERITY.items()
        }
        payload["total_area_ha"] = round(float((mask > 0).sum()) * pixel_ha, 2)
        payload["area_low_ha"] = areas["low"]
        payload["area_moderate_ha"] = areas["moderate"]
        payload["area_high_ha"] = areas["high"]
        payload["area_ha"] = {"prediction": areas, "ground_truth": gt_areas}
        payload["polygons"] = (
            class_features(
                mask,
                georef,
                classes=SEVERITY,
                scene_id=chip_id,
                model_version=result["model_version"],
                source=SOURCE_PRED,
                simplify_m=georef.gsd_x / 2,
            )
            if georef
            else []
        )
        payload["ground_truth_polygons"] = (
            class_features(
                gt,
                georef,
                classes=SEVERITY,
                scene_id=chip_id,
                model_version="official_train_gt",
                source=SOURCE_GT,
                simplify_m=georef.gsd_x / 2,
            )
            if georef
            else []
        )
        payload["n_fire_px"] = None
        payload["confidence_mean"] = None
        payload["thermopoints"] = []
    payload["mask_available"] = True
    payload["runtime_ms"] = {
        "model": round(float(ml_ms), 1),
        "vectorize": round((time.perf_counter() - t_geo) * 1000, 1),
        "total": round((time.perf_counter() - started) * 1000, 1),
    }
    return payload


def overlay_png(kind: str, chip_id: str, layer: Layer, size: int = 512) -> bytes:
    chip, _ = _chip(chip_id)
    if chip["kind"] != kind:
        raise HTTPException(status_code=422, detail=f"{chip_id} is a {chip['kind'].upper()} chip")
    result = _run(kind, chip_id)
    mask = result["mask"].astype(np.int64)
    gt = np.where(result["gt_mask"] == 255, 0, result["gt_mask"]).astype(np.int64)
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    if layer == "error":
        pred_b, truth_b = mask > 0, gt > 0
        if kind == "af":
            rgba[pred_b & truth_b] = COLORS["tp"]
        rgba[pred_b & ~truth_b] = COLORS["fp"]
        rgba[~pred_b & truth_b] = COLORS["fn"]
        if kind == "bs":
            rgba[pred_b & truth_b & (mask != gt)] = COLORS["wrong"]
    else:
        source = mask if layer == "pred" else gt
        if kind == "af":
            rgba[source > 0] = COLORS["fire"]
        else:
            for k, name in SEVERITY.items():
                rgba[source == k] = COLORS[name]
    image = Image.fromarray(rgba, mode="RGBA").resize((size, size), Image.Resampling.NEAREST)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def feature_collection(kind: str, chip_id: str, layer: Literal["pred", "gt"]) -> dict[str, Any]:
    payload = prediction_payload(kind, chip_id)
    if kind == "af":
        features = payload["thermopoints"] if layer == "pred" else []
    else:
        features = payload["polygons"] if layer == "pred" else payload["ground_truth_polygons"]
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
        "properties": {
            "scene_id": chip_id,
            "model_version": payload["model_version"],
            "layer": layer,
            "prediction": SCOPE,
            "area_ha": payload.get("area_ha"),
        },
    }
