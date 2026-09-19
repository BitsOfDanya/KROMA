from __future__ import annotations

import logging
import time
from collections import OrderedDict
from functools import lru_cache
from threading import Lock
from typing import Any, Literal

from kroma_ml import artifacts

Kind = Literal["af", "bs"]
logger = logging.getLogger(__name__)
CACHE_SIZE = 12


class MlUnavailableError(RuntimeError):
    pass


class MlService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
        self._loaded: dict[str, float] = {}

    def status(self) -> dict[str, Any]:
        state = artifacts.status()
        manifest = artifacts.read_manifest()
        files = state["files"]
        bs_keys = artifacts.BS_KEYS
        return {
            "artifacts_root": state["artifacts_root"],
            "af": {
                "ready": state["af"]["ready"],
                "path": files["af_model"]["path"],
                "model_version": state["af"]["model_version"],
                "expected": "LightGBM · 39 признаков · corrected validity · OOF hard negatives",
            },
            "bs": {
                "ready": state["bs"]["ready"],
                "paths": {key: files[key]["path"] for key in bs_keys},
                "present": {key: files[key]["present"] for key in bs_keys},
                "model_version": state["bs"]["model_version"],
                "expected": (
                    "U-Net ensemble v003 → physics/dNBR + LightGBM refiner v004 → "
                    "component filter → contour refiner v005"
                ),
            },
            "files": files,
            "provenance": manifest.get("provenance", {}),
            "load_seconds": dict(self._loaded),
            "note": (
                "Веса не входят в git. Смонтируйте их: python scripts/mount_artifacts.py "
                "или задайте KROMA_ML_ARTIFACTS_PATH."
                if not (state["af"]["ready"] and state["bs"]["ready"])
                else "Модели готовы; сервис вызывает тот же пайплайн, что и inference.py."
            ),
        }

    def ready(self, kind: Kind) -> bool:
        return bool(artifacts.status()[kind]["ready"])

    def run(self, kind: Kind, chip_id: str) -> dict[str, Any]:
        key = (kind, chip_id)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if not self.ready(kind):
                missing = [
                    name
                    for name, item in artifacts.status()["files"].items()
                    if not item["present"] and (name == "af_model") == (kind == "af")
                ]
                raise MlUnavailableError(
                    f"{kind.upper()} weights are not mounted; missing: {', '.join(missing)}"
                )
            try:
                from kroma_ml import service

                started = time.perf_counter()
                result = (
                    service.predict_af(chip_id) if kind == "af" else service.predict_bs(chip_id)
                )
                self._loaded.setdefault(kind, round(time.perf_counter() - started, 2))
            except FileNotFoundError as error:
                raise MlUnavailableError(f"input data for {chip_id} not found: {error}") from error
            except Exception as error:
                logger.exception("ml_inference_failed kind=%s chip=%s", kind, chip_id)
                raise MlUnavailableError(f"{kind.upper()} inference failed: {error}") from error
            self._cache[key] = result
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
            return result


@lru_cache
def get_ml_service() -> MlService:
    return MlService()
