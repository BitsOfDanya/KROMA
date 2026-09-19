"""Decode uploaded rasters / images for ML upload inference."""

from __future__ import annotations

import base64
import io
from typing import Any

import numpy as np
from fastapi import HTTPException
from PIL import Image

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def decode_upload(filename: str, data: bytes) -> dict[str, Any]:
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 64 МБ")

    name = (filename or "upload.bin").lower()
    array: np.ndarray
    kind = "image"

    if name.endswith((".tif", ".tiff")) or data[:2] in (b"II", b"MM"):
        try:
            import tifffile

            array = np.asarray(tifffile.imread(io.BytesIO(data)))
            kind = "geotiff"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось прочитать GeoTIFF: {exc}",
            ) from exc
    else:
        try:
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
            array = np.asarray(img)
            kind = "image"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось прочитать изображение: {exc}",
            ) from exc

    preview = _preview_png(array)
    shape = list(array.shape)
    if array.ndim == 2:
        bands = 1
    elif array.ndim == 3 and array.shape[0] <= 12:
        bands = array.shape[0]
    else:
        bands = array.shape[-1]
    return {
        "filename": filename,
        "kind": kind,
        "shape": shape,
        "dtype": str(array.dtype),
        "bands": int(bands),
        "nbytes": int(array.nbytes),
        "preview_png_b64": base64.b64encode(preview).decode("ascii"),
        "array": array,
    }


def mask_to_png_b64(mask: np.ndarray, *, binary: bool = False) -> str:
    from app.services.train_dataset import _colorize_mask

    arr = np.asarray(mask)
    if arr.ndim > 2:
        arr = arr.squeeze()
    if arr.ndim != 2:
        raise ValueError("mask must be 2D")
    if binary:
        arr = (arr > 0).astype(np.uint8)
    else:
        arr = arr.astype(np.uint8)
    png = io.BytesIO()
    _colorize_mask(arr).save(png, format="PNG")
    return base64.b64encode(png.getvalue()).decode("ascii")


def _preview_png(arr: np.ndarray, size: int = 512) -> bytes:
    if arr.ndim == 2:
        plane = arr.astype(np.float32)
        rgb = np.stack([_stretch(plane)] * 3, axis=-1)
    else:
        channel_first = arr.shape[0] < arr.shape[-1] and arr.shape[0] <= 16
        data = np.moveaxis(arr, 0, -1) if channel_first else arr
        if data.ndim == 3 and data.shape[-1] >= 3:
            rgb = np.stack(
                [_stretch(data[..., i].astype(np.float32)) for i in (0, 1, 2)],
                axis=-1,
            )
        elif data.ndim == 3:
            plane = data[..., 0].astype(np.float32)
            rgb = np.stack([_stretch(plane)] * 3, axis=-1)
        else:
            rgb = np.stack([_stretch(arr.astype(np.float32))] * 3, axis=-1)

    img = Image.fromarray(rgb, mode="RGB")
    img = img.resize((size, size), Image.Resampling.BILINEAR)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _stretch(plane: np.ndarray) -> np.ndarray:
    finite = plane[np.isfinite(plane)]
    if finite.size == 0:
        return np.zeros(plane.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, (2, 98))
    if hi <= lo:
        hi = lo + 1
    scaled = np.clip((plane - lo) / (hi - lo), 0, 1)
    return (scaled * 255).astype(np.uint8)
