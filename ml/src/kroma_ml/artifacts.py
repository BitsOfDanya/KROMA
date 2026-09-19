import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = REPO / "ml" / "artifacts"
EXPERIMENTS = REPO / "research" / "experiments"

AF_VERSION = "af-v001 (full-train LightGBM, 39 features, threshold 0.765; unchanged in v001-v005)"
BS_VERSION = "bs-v005 (v003 U-Net ensemble -> v004 refiner+physics -> component filter -> refiner2)"


ARTIFACTS: dict[str, tuple[str, Path]] = {
    "af_model": ("af/af_fulltrain_model.joblib", EXPERIMENTS / "af_fulltrain_model.joblib"),
    "bs_neural_ndvi": (
        "bs/neural/bs_full_ndvi_ohem40.pt",
        EXPERIMENTS / "bs_full_ndvi_ohem40.pt",
    ),
    "bs_neural_dual": ("bs/neural/bs_full_dual.pt", EXPERIMENTS / "bs_full_dual.pt"),
    "bs_thresholds": (
        "bs/physics_thresholds.json",
        EXPERIMENTS / "bs_v004_physics_thresholds.json",
    ),
    "bs_v004_refiner": (
        "bs/v004_refiner.txt",
        REPO / "data/processed/bs_v004/refiner_full_v004.txt",
    ),
    "bs_component": (
        "bs/v005_component.txt",
        REPO / "data/processed/bs_v005/components/component_full_v005b_candidate.txt",
    ),
    "bs_refiner2": (
        "bs/v005_refiner2.txt",
        REPO / "data/processed/bs_v005/refiner2/refiner2_full_v005b_candidate.txt",
    ),
}
AF_KEYS = ("af_model",)
BS_KEYS = tuple(k for k in ARTIFACTS if k.startswith("bs_"))


def artifacts_root() -> Path:
    return Path(os.environ.get("KROMA_ML_ARTIFACTS_PATH") or DEFAULT_ROOT)


def resolve(key: str) -> Path:
    relative, fallback = ARTIFACTS[key]
    mounted = artifacts_root() / relative
    if mounted.is_file():
        return mounted
    return fallback if fallback.is_file() else mounted


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest() -> dict:
    path = artifacts_root() / "manifest.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def status(verify_hashes: bool = False) -> dict:
    manifest = read_manifest().get("files", {})
    files = {}
    for key in ARTIFACTS:
        path = resolve(key)
        entry = {"path": _display(path), "present": path.is_file()}
        if path.is_file():
            entry["bytes"] = path.stat().st_size
            expected = manifest.get(key, {}).get("sha256")
            if expected:
                entry["sha256_expected"] = expected
                if verify_hashes:
                    entry["sha256_ok"] = sha256(path) == expected
        files[key] = entry
    af_ready = all(files[k]["present"] for k in AF_KEYS)
    bs_ready = all(files[k]["present"] for k in BS_KEYS)
    return {
        "artifacts_root": _display(artifacts_root()),
        "af": {"ready": af_ready, "model_version": AF_VERSION if af_ready else None},
        "bs": {"ready": bs_ready, "model_version": BS_VERSION if bs_ready else None},
        "files": files,
    }


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)
