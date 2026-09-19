"""ML inference adapter — loads artifacts once; safe if weights are missing."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Literal

Kind = Literal["af", "bs"]


@dataclass(frozen=True)
class AFResult:
    chip_id: str
    model_version: str
    runtime_ms: float
    n_fire_px: int
    confidence_mean: float | None
    thermopoints: list[dict[str, Any]] = field(default_factory=list)
    mask_available: bool = False
    status: Literal["ok", "unavailable"] = "ok"
    detail: str | None = None


@dataclass(frozen=True)
class BSResult:
    chip_id: str
    model_version: str
    runtime_ms: float
    total_area_ha: float | None
    area_low_ha: float | None
    area_moderate_ha: float | None
    area_high_ha: float | None
    polygons: list[dict[str, Any]] = field(default_factory=list)
    mask_available: bool = False
    status: Literal["ok", "unavailable"] = "ok"
    detail: str | None = None


class MlUnavailableError(RuntimeError):
    """Raised when artifacts are not mounted or inference cannot run."""


class MlService:
    """Single-process adapter. Weights load once under lock.

    Expected layout (optional until ML team mounts weights):
      {artifacts}/af/lightgbm.joblib
      {artifacts}/bs/model_a.pt
      {artifacts}/bs/model_b.pt
      {artifacts}/bs/refiner.joblib
      {artifacts}/bs/calibration.json
    """

    def __init__(self, artifacts_root: Path | None = None) -> None:
        root = artifacts_root or Path(
            os.environ.get("KROMA_ML_ARTIFACTS_PATH", "")
            or Path(__file__).resolve().parents[3] / "ml" / "artifacts"
        )
        self.artifacts_root = root
        self._lock = Lock()
        self._af_model: Any = None
        self._bs_bundle: Any = None
        self._af_version = "af-unavailable"
        self._bs_version = "bs-unavailable"

    def status(self) -> dict[str, Any]:
        af_path = self.artifacts_root / "af" / "lightgbm.joblib"
        bs_paths = {
            "model_a": self.artifacts_root / "bs" / "model_a.pt",
            "model_b": self.artifacts_root / "bs" / "model_b.pt",
            "refiner": self.artifacts_root / "bs" / "refiner.joblib",
            "calibration": self.artifacts_root / "bs" / "calibration.json",
        }
        return {
            "artifacts_root": str(self.artifacts_root),
            "af": {
                "ready": af_path.is_file(),
                "path": str(af_path),
                "model_version": self._af_version if af_path.is_file() else None,
                "expected": "LightGBM corrected validity · 39 features · OOF HNM",
            },
            "bs": {
                "ready": all(p.is_file() for p in bs_paths.values()),
                "paths": {k: str(v) for k, v in bs_paths.items()},
                "present": {k: v.is_file() for k, v in bs_paths.items()},
                "model_version": self._bs_version if all(p.is_file() for p in bs_paths.values()) else None,
                "expected": "Attention U-Net ensemble → physics/dNBR → LightGBM refiner (GOLD/v004)",
            },
            "note": (
                "Weights are not shipped in this checkout. Mount ml/artifacts or set "
                "KROMA_ML_ARTIFACTS_PATH. Train GT and footprints work without weights."
            ),
        }

    def _ensure_af(self) -> None:
        with self._lock:
            if self._af_model is not None:
                return
            path = self.artifacts_root / "af" / "lightgbm.joblib"
            if not path.is_file():
                raise MlUnavailableError(
                    f"AF artifact missing: {path}. Mount LightGBM joblib under ml/artifacts/af/."
                )
            import joblib  # lazy

            self._af_model = joblib.load(path)
            meta = self.artifacts_root / "af" / "version.txt"
            self._af_version = meta.read_text().strip() if meta.is_file() else "af-lightgbm-current"

    def _ensure_bs(self) -> None:
        with self._lock:
            if self._bs_bundle is not None:
                return
            required = [
                self.artifacts_root / "bs" / "model_a.pt",
                self.artifacts_root / "bs" / "model_b.pt",
                self.artifacts_root / "bs" / "refiner.joblib",
                self.artifacts_root / "bs" / "calibration.json",
            ]
            missing = [str(p) for p in required if not p.is_file()]
            if missing:
                raise MlUnavailableError(
                    "BS artifacts missing: " + ", ".join(missing)
                )
            # Torch + LightGBM may need a subprocess boundary on some hosts.
            # Load is deferred to kroma_ml.inference.bs when the package provides it.
            try:
                from kroma_ml.inference.bs import load_bs_bundle  # type: ignore
            except ImportError as exc:
                raise MlUnavailableError(
                    "kroma_ml.inference.bs is not implemented yet; "
                    "keep weights in ml/artifacts/bs and add the inference module."
                ) from exc
            self._bs_bundle = load_bs_bundle(self.artifacts_root / "bs")
            meta = self.artifacts_root / "bs" / "version.txt"
            self._bs_version = meta.read_text().strip() if meta.is_file() else "bs-gold-v004"

    def predict_af(self, chip_id: str, chip_payload: dict[str, Any] | None = None) -> AFResult:
        started = time.perf_counter()
        try:
            self._ensure_af()
        except MlUnavailableError as exc:
            return AFResult(
                chip_id=chip_id,
                model_version="unavailable",
                runtime_ms=(time.perf_counter() - started) * 1000,
                n_fire_px=0,
                confidence_mean=None,
                status="unavailable",
                detail=str(exc),
            )
        try:
            from kroma_ml.inference.af import predict_af_chip  # type: ignore

            raw = predict_af_chip(self._af_model, chip_id, chip_payload)
            return AFResult(
                chip_id=chip_id,
                model_version=self._af_version,
                runtime_ms=(time.perf_counter() - started) * 1000,
                n_fire_px=int(raw.get("n_fire_px", 0)),
                confidence_mean=raw.get("confidence_mean"),
                thermopoints=list(raw.get("thermopoints", [])),
                mask_available=bool(raw.get("mask_available")),
                status="ok",
            )
        except Exception as exc:  # noqa: BLE001 — surface as unavailable for demo safety
            return AFResult(
                chip_id=chip_id,
                model_version=self._af_version,
                runtime_ms=(time.perf_counter() - started) * 1000,
                n_fire_px=0,
                confidence_mean=None,
                status="unavailable",
                detail=f"AF inference failed: {exc}",
            )

    def predict_bs(self, chip_id: str, scene_payload: dict[str, Any] | None = None) -> BSResult:
        started = time.perf_counter()
        try:
            self._ensure_bs()
        except MlUnavailableError as exc:
            return BSResult(
                chip_id=chip_id,
                model_version="unavailable",
                runtime_ms=(time.perf_counter() - started) * 1000,
                total_area_ha=None,
                area_low_ha=None,
                area_moderate_ha=None,
                area_high_ha=None,
                status="unavailable",
                detail=str(exc),
            )
        try:
            from kroma_ml.inference.bs import predict_bs_scene  # type: ignore

            raw = predict_bs_scene(self._bs_bundle, chip_id, scene_payload)
            return BSResult(
                chip_id=chip_id,
                model_version=self._bs_version,
                runtime_ms=(time.perf_counter() - started) * 1000,
                total_area_ha=raw.get("total_area_ha"),
                area_low_ha=raw.get("area_low_ha"),
                area_moderate_ha=raw.get("area_moderate_ha"),
                area_high_ha=raw.get("area_high_ha"),
                polygons=list(raw.get("polygons", [])),
                mask_available=bool(raw.get("mask_available")),
                status="ok",
            )
        except Exception as exc:  # noqa: BLE001
            return BSResult(
                chip_id=chip_id,
                model_version=self._bs_version,
                runtime_ms=(time.perf_counter() - started) * 1000,
                total_area_ha=None,
                area_low_ha=None,
                area_moderate_ha=None,
                area_high_ha=None,
                status="unavailable",
                detail=f"BS inference failed: {exc}",
            )

    def predict_upload(self, task: Kind, filename: str, data: bytes) -> dict[str, Any]:
        """Run AF/BS on an uploaded raster/image. Returns JSON-serializable payload."""
        from app.services.upload_decode import decode_upload, mask_to_png_b64

        started = time.perf_counter()
        decoded = decode_upload(filename, data)
        array = decoded.pop("array")
        chip_id = f"upload:{filename}"
        payload = {"array": array, "filename": filename, "shape": decoded["shape"]}

        if task == "af":
            try:
                self._ensure_af()
                from kroma_ml.inference.af import predict_af_chip  # type: ignore

                raw = predict_af_chip(self._af_model, chip_id, payload)
                mask_b64 = None
                if raw.get("mask") is not None:
                    mask_b64 = mask_to_png_b64(raw["mask"], binary=True)
                return {
                    "task": "af",
                    "input": decoded,
                    "status": "ok",
                    "detail": None,
                    "model_version": self._af_version,
                    "runtime_ms": (time.perf_counter() - started) * 1000,
                    "n_fire_px": int(raw.get("n_fire_px", 0)),
                    "confidence_mean": raw.get("confidence_mean"),
                    "thermopoints": list(raw.get("thermopoints", [])),
                    "mask_png_b64": mask_b64,
                    "metrics": {
                        "n_fire_px": int(raw.get("n_fire_px", 0)),
                        "confidence_mean": raw.get("confidence_mean"),
                    },
                }
            except MlUnavailableError as exc:
                return {
                    "task": "af",
                    "input": decoded,
                    "status": "unavailable",
                    "detail": str(exc),
                    "model_version": "unavailable",
                    "runtime_ms": (time.perf_counter() - started) * 1000,
                    "n_fire_px": 0,
                    "confidence_mean": None,
                    "thermopoints": [],
                    "mask_png_b64": None,
                    "metrics": {"n_fire_px": 0, "confidence_mean": None},
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "task": "af",
                    "input": decoded,
                    "status": "unavailable",
                    "detail": f"AF inference failed: {exc}",
                    "model_version": self._af_version,
                    "runtime_ms": (time.perf_counter() - started) * 1000,
                    "n_fire_px": 0,
                    "confidence_mean": None,
                    "thermopoints": [],
                    "mask_png_b64": None,
                    "metrics": {"n_fire_px": 0, "confidence_mean": None},
                }

        try:
            self._ensure_bs()
            from kroma_ml.inference.bs import predict_bs_scene  # type: ignore

            raw = predict_bs_scene(self._bs_bundle, chip_id, payload)
            mask_b64 = None
            if raw.get("mask") is not None:
                mask_b64 = mask_to_png_b64(raw["mask"], binary=False)
            return {
                "task": "bs",
                "input": decoded,
                "status": "ok",
                "detail": None,
                "model_version": self._bs_version,
                "runtime_ms": (time.perf_counter() - started) * 1000,
                "total_area_ha": raw.get("total_area_ha"),
                "area_low_ha": raw.get("area_low_ha"),
                "area_moderate_ha": raw.get("area_moderate_ha"),
                "area_high_ha": raw.get("area_high_ha"),
                "polygons": list(raw.get("polygons", [])),
                "mask_png_b64": mask_b64,
                "metrics": {
                    "total_area_ha": raw.get("total_area_ha"),
                    "area_low_ha": raw.get("area_low_ha"),
                    "area_moderate_ha": raw.get("area_moderate_ha"),
                    "area_high_ha": raw.get("area_high_ha"),
                },
            }
        except MlUnavailableError as exc:
            return {
                "task": "bs",
                "input": decoded,
                "status": "unavailable",
                "detail": str(exc),
                "model_version": "unavailable",
                "runtime_ms": (time.perf_counter() - started) * 1000,
                "total_area_ha": None,
                "area_low_ha": None,
                "area_moderate_ha": None,
                "area_high_ha": None,
                "polygons": [],
                "mask_png_b64": None,
                "metrics": {
                    "total_area_ha": None,
                    "area_low_ha": None,
                    "area_moderate_ha": None,
                    "area_high_ha": None,
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "task": "bs",
                "input": decoded,
                "status": "unavailable",
                "detail": f"BS inference failed: {exc}",
                "model_version": self._bs_version,
                "runtime_ms": (time.perf_counter() - started) * 1000,
                "total_area_ha": None,
                "area_low_ha": None,
                "area_moderate_ha": None,
                "area_high_ha": None,
                "polygons": [],
                "mask_png_b64": None,
                "metrics": {
                    "total_area_ha": None,
                    "area_low_ha": None,
                    "area_moderate_ha": None,
                    "area_high_ha": None,
                },
            }


@lru_cache
def get_ml_service() -> MlService:
    return MlService()
