"""Official TRAIN dataset access — footprints, metadata, raster previews from tar."""

from __future__ import annotations

import csv
import io
import json
import os
import tarfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import HTTPException
from kroma_geo.raster_vector import ChipGeoreference
from PIL import Image

from app.services.ml_service import get_ml_service

Asset = Literal[
    "mask",
    "viirs",
    "aux",
    "s2_pre",
    "s2_post",
    "s1_pre",
    "s1_post",
]

ASSET_PATHS: dict[str, dict[Asset, str]] = {
    "af": {
        "mask": "train/af/masks/{id}_MASK.tif",
        "viirs": "train/af/viirs/{id}_VIIRS_I1-I5.tif",
        "aux": "train/af/aux/{id}_AUX.tif",
    },
    "bs": {
        "mask": "train/bs/masks/{id}_MASK.tif",
        "aux": "train/bs/aux/{id}_AUX.tif",
        "s2_pre": "train/bs/sentinel2_pre/{id}_Sentinel-2_pre.tif",
        "s2_post": "train/bs/sentinel2_post/{id}_Sentinel-2_post.tif",
        "s1_pre": "train/bs/sentinel1_pre/{id}_Sentinel-1_pre.tif",
        "s1_post": "train/bs/sentinel1_post/{id}_Sentinel-1_post.tif",
    },
}


class TrainDatasetService:
    def __init__(self, index_path: Path, tar_path: Path, train_dir: Path | None = None) -> None:
        self.index_path = index_path
        self.tar_path = tar_path
        self.train_dir = train_dir
        self._chips: dict[str, dict[str, Any]] = {}
        self._georef: dict[str, ChipGeoreference] | None = None
        self._load()

    @property
    def directory_present(self) -> bool:
        return bool(self.train_dir and (self.train_dir / "af").is_dir())

    @property
    def source(self) -> str | None:
        if self.directory_present:
            return "directory"
        return "tar" if self.tar_path.is_file() else None

    def georef(self, chip_id: str) -> ChipGeoreference | None:
        """UTM raster origin from the official meta.csv (authoritative for prediction geometry)."""
        if self._georef is None:
            self._georef = {}
            for kind in ("af", "bs"):
                path = self.train_dir / kind / "meta.csv" if self.train_dir else None
                if not path or not path.is_file():
                    continue
                with path.open(newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle):
                        try:
                            gsd = float(row["gsd"])
                            self._georef[row["chip_id"]] = ChipGeoreference(
                                epsg=int(float(row["epsg"])),
                                x_min=float(row["x_min"]),
                                y_max=float(row["y_max"]),
                                gsd_x=gsd,
                                gsd_y=gsd,
                            )
                        except (KeyError, ValueError):
                            continue
        return self._georef.get(chip_id)

    def _load(self) -> None:
        if not self.index_path.is_file():
            return
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        for chip in payload.get("chips", []):
            self._chips[chip["chip_id"]] = chip

    def reload(self) -> None:
        self._chips.clear()
        self._load()

    def summary(self) -> dict[str, Any]:
        return {
            "dataset": "official_train",
            "label": "OFFICIAL TRAIN",
            "origin": "official_train",
            "available": bool(self._chips) and self.source is not None,
            "source": self.source,
            "directory_present": self.directory_present,
            "tar_present": self.tar_path.is_file(),
            "index_present": self.index_path.is_file(),
            "counts": {
                "total": len(self._chips),
                "af": sum(1 for c in self._chips.values() if c.get("kind") == "af"),
                "bs": sum(1 for c in self._chips.values() if c.get("kind") == "bs"),
            },
            "note": "Competition test is anonymized and never served on the map.",
        }

    def list_chips(
        self,
        *,
        kind: Literal["af", "bs"] | None = None,
        has_fire: bool | None = None,
        q: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        items = list(self._chips.values())
        if kind:
            items = [c for c in items if c.get("kind") == kind]
        if has_fire is not None and kind == "af":
            items = [c for c in items if bool(c.get("has_fire")) is has_fire]
        if q:
            needle = q.lower()
            items = [
                c
                for c in items
                if needle in c["chip_id"].lower()
                or needle in str(c.get("fire_event_id") or "").lower()
                or needle in str(c.get("satellite") or "").lower()
            ]
        items.sort(key=lambda c: c["chip_id"])
        total = len(items)
        page = items[offset : offset + limit]
        # strip heavy geometry for list if huge — keep footprint for map sync
        return {"total": total, "offset": offset, "limit": limit, "items": page}

    def get_chip(self, chip_id: str) -> dict[str, Any]:
        chip = self._chips.get(chip_id)
        if not chip:
            raise HTTPException(status_code=404, detail=f"Unknown train chip: {chip_id}")
        kind = chip["kind"]
        assets = list(ASSET_PATHS.get(kind, {}).keys())
        prediction_ready = (
            self.directory_present
            and self.georef(chip_id) is not None
            and bool(get_ml_service().ready(kind))
        )
        return {
            **chip,
            "assets": assets,
            "inspector": {
                "modes": (
                    ["ground_truth", "layers"]
                    if kind == "af"
                    else ["before_after", "ground_truth", "layers"]
                ),
                "prediction_available": prediction_ready,
                "prediction_note": (
                    "Предсказание финальной модели (in-sample: модель обучена на всех train-чипах)."
                    if prediction_ready
                    else "Веса не смонтированы или нет растров: python scripts/mount_artifacts.py."
                ),
            },
        }

    def _member_for(self, chip_id: str, asset: Asset) -> str:
        chip = self.get_chip(chip_id)
        kind = chip["kind"]
        template = ASSET_PATHS.get(kind, {}).get(asset)
        if not template:
            raise HTTPException(status_code=404, detail=f"Asset {asset} not available for {kind}")
        return template.format(id=chip_id)

    def read_bytes(self, chip_id: str, asset: Asset) -> bytes:
        member = self._member_for(chip_id, asset)
        if self.directory_present:
            path = self.train_dir.parent / member  # templates are "train/<kind>/..."
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"Missing {member}")
            return path.read_bytes()
        if not self.tar_path.is_file():
            raise HTTPException(status_code=503, detail="Train data not available on server")
        with tarfile.open(self.tar_path, "r:") as tf:
            try:
                f = tf.extractfile(member)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=f"Missing {member}") from exc
            if f is None:
                raise HTTPException(status_code=404, detail=f"Missing {member}")
            return f.read()

    def preview_png(self, chip_id: str, asset: Asset, size: int = 512) -> bytes:
        import tifffile

        blob = self.read_bytes(chip_id, asset)
        arr = tifffile.imread(io.BytesIO(blob))
        img = _array_to_preview(arr, asset)
        resampling = (
            Image.Resampling.NEAREST if asset == "mask" else Image.Resampling.BILINEAR
        )
        img = img.resize((size, size), resampling)
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()


def _array_to_preview(arr: np.ndarray, asset: Asset) -> Image.Image:
    if arr.ndim == 2:
        if asset == "mask":
            return _colorize_mask(arr)
        plane = arr.astype(np.float32)
        return Image.fromarray(_stretch(plane), mode="L").convert("RGB")
    # multi-band
    data = np.moveaxis(arr, 0, -1) if arr.shape[0] < arr.shape[-1] and arr.shape[0] <= 12 else arr
    if data.ndim == 3 and data.shape[-1] >= 3:
        # prefer reflective-looking bands; for VIIRS take first 3
        rgb = np.stack([_stretch(data[..., i].astype(np.float32)) for i in (0, 1, 2)], axis=-1)
        return Image.fromarray(rgb, mode="RGB")
    if data.ndim == 3:
        plane = data[..., 0].astype(np.float32)
        return Image.fromarray(_stretch(plane), mode="L").convert("RGB")
    return Image.fromarray(_stretch(arr.astype(np.float32)), mode="L").convert("RGB")


def _stretch(plane: np.ndarray) -> np.ndarray:
    finite = plane[np.isfinite(plane)]
    if finite.size == 0:
        return np.zeros(plane.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, (2, 98))
    if hi <= lo:
        hi = lo + 1
    scaled = np.clip((plane - lo) / (hi - lo), 0, 1)
    return (scaled * 255).astype(np.uint8)


def _colorize_mask(mask: np.ndarray) -> Image.Image:
    """AF: 0/1. BS severity: 0/1/2/3 → transparent / low / mod / high."""
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    # low
    rgba[mask == 1] = (232, 176, 88, 200)
    # moderate
    rgba[mask == 2] = (232, 120, 64, 220)
    # high / AF fire
    rgba[mask == 3] = (220, 56, 48, 235)
    # AF binary fire as high
    if set(np.unique(mask)).issubset({0, 1}):
        rgba[mask == 1] = (220, 56, 48, 220)
    return Image.fromarray(rgba, mode="RGBA")


@lru_cache
def get_train_dataset_service() -> TrainDatasetService:
    root = Path(__file__).resolve().parents[3]
    default_dir = root / "data" / "Мониторинг DATA" / "train"
    train_dir = Path(os.environ.get("KROMA_TRAIN_ROOT") or default_dir)
    return TrainDatasetService(
        index_path=root / "data" / "fire-aoi" / "train_chips_index.json",
        tar_path=root / "data" / "yandex" / "fire-train-renamed.tar",
        train_dir=train_dir,
    )
