"""Run the official AF/BS models on a user supplied chip archive."""

from __future__ import annotations

import base64
import io
import re
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Literal

import numpy as np
import tifffile
from fastapi import HTTPException

from app.services.upload_decode import MAX_UPLOAD_BYTES, _preview_png, mask_to_png_b64

MAX_UNPACKED_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 20
ASSETS = {
    "af": {"viirs": ("VIIRS_I1-I5", 8), "aux": ("AUX", 5)},
    "bs": {
        "sentinel2_pre": ("Sentinel-2_pre", 10),
        "sentinel2_post": ("Sentinel-2_post", 10),
        "sentinel1_pre": ("Sentinel-1_pre", 2),
        "sentinel1_post": ("Sentinel-1_post", 2),
        "aux": ("AUX", 3),
    },
}


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _read_archive(task: str, data: bytes) -> tuple[str, dict[str, bytes], np.ndarray]:
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ZIP больше 64 МБ")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise _bad("Загрузите ZIP с TIFF-каналами чипа, а не отдельное изображение")
    expected = ASSETS[task]
    found: dict[str, bytes] = {}
    chip_ids: set[str] = set()
    preview: np.ndarray | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = [member for member in archive.infolist() if not member.is_dir()]
            if (
                len(files) > MAX_MEMBERS
                or sum(member.file_size for member in files) > MAX_UNPACKED_BYTES
            ):
                raise HTTPException(status_code=413, detail="Содержимое ZIP слишком велико")
            for member in files:
                basename = Path(member.filename).name
                for folder, (suffix, bands) in expected.items():
                    match = re.fullmatch(
                        rf"([A-Za-z0-9_-]{{1,80}})_{re.escape(suffix)}\.tif",
                        basename,
                        re.IGNORECASE,
                    )
                    if not match:
                        continue
                    if folder in found:
                        raise _bad(f"В ZIP несколько файлов {suffix}")
                    chip_ids.add(match.group(1))
                    blob = archive.read(member)
                    try:
                        with tifffile.TiffFile(io.BytesIO(blob)) as tif:
                            series = tif.series[0]
                            if series.shape != (256, 256, bands) or not np.issubdtype(
                                series.dtype, np.number
                            ):
                                raise _bad(f"{basename}: ожидается TIFF 256×256×{bands} каналов")
                            array = series.asarray()
                    except HTTPException:
                        raise
                    except Exception as exc:
                        raise _bad(f"Не удалось прочитать {basename}: {exc}") from exc
                    if preview is None and folder in ("viirs", "sentinel2_post"):
                        preview = array
                    found[folder] = blob
                    break
    except zipfile.BadZipFile as exc:
        raise _bad("Повреждённый ZIP") from exc
    missing = [suffix for folder, (suffix, _) in expected.items() if folder not in found]
    if missing:
        raise _bad("В ZIP отсутствуют: " + ", ".join(missing))
    if len(chip_ids) != 1:
        raise _bad("Все TIFF в ZIP должны иметь один и тот же ID чипа")
    assert preview is not None
    return chip_ids.pop(), found, preview


def predict_upload(task: Literal["af", "bs"], filename: str, data: bytes) -> dict:
    started = time.perf_counter()
    chip_id, assets, preview = _read_archive(task, data)
    from kroma_ml import service

    with tempfile.TemporaryDirectory(prefix="kroma-upload-") as temp:
        for folder, (suffix, _) in ASSETS[task].items():
            target = Path(temp) / folder / f"{chip_id}_{suffix}.tif"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(assets[folder])
        try:
            result = (
                service.predict_af(chip_id, root=temp)
                if task == "af"
                else service.predict_bs(chip_id, root=temp)
            )
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Не удалось выполнить предикт для этого чипа: {exc}"
            ) from exc
    response = {
        "task": task,
        "input": {
            "filename": filename,
            "kind": "chip_zip",
            "chip_id": chip_id,
            "shape": [256, 256],
            "preview_png_b64": base64.b64encode(_preview_png(preview)).decode("ascii"),
        },
        "status": "ok",
        "detail": "Предикт по загруженным данным. Метрики недоступны без разметки.",
        "model_version": result["model_version"],
        "runtime_ms": round((time.perf_counter() - started) * 1000, 1),
        "mask_png_b64": mask_to_png_b64(result["mask"], binary=task == "af"),
        "metrics": {},
    }
    if task == "af":
        response["n_fire_px"] = result["fire_pixels"]
        selected = result["mask"].astype(bool)
        response["confidence_mean"] = (
            float(result["probability"][selected].mean()) if selected.any() else None
        )
    else:
        response["total_area_ha"] = result["total_burned_area_ha"]
        for severity in ("low", "moderate", "high"):
            response[f"area_{severity}_ha"] = result["area_ha"][severity]
    return response
