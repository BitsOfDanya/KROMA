import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np

from kroma_ml import artifacts
from kroma_ml.artifacts import AF_VERSION, BS_VERSION, REPO, resolve

BS_RULE = {"comp_remove_below": 0.3, "refiner2_add_at_or_above": 0.8, "refiner2_remove_below": 0.2}
NEURAL_DEVICE = "auto"
PIXEL_HA = 20 * 20 / 10_000


def data_root(split: str) -> Path:
    if split == "test":
        return Path(os.environ.get("KROMA_TEST_ROOT") or REPO / "data" / "test")
    return Path(os.environ.get("KROMA_TRAIN_ROOT") or REPO / "data" / "Мониторинг DATA" / "train")


def resolve_root(chip_id: str, kind: str, root: str | None) -> tuple[str, bool]:
    if root:
        return root, False
    split = "test" if "_te_" in chip_id else "train"
    return str(data_root(split) / kind), split == "train"


def status(verify_hashes: bool = False) -> dict:
    return artifacts.status(verify_hashes)


@lru_cache(maxsize=1)
def af_bundle() -> dict:
    import joblib

    return joblib.load(resolve("af_model"))


def predict_af(chip_id: str, root: str | None = None) -> dict:
    from kroma_ml.af_data import load_chip, valid_mask
    from kroma_ml.af_features import chip_feature_stack

    started = time.perf_counter()
    root, has_gt = resolve_root(chip_id, "af", root)
    chip = load_chip(chip_id, root=root, with_mask=has_gt)
    bundle = af_bundle()
    stack = chip_feature_stack(chip)
    h, w, c = stack.shape
    proba = bundle["model"].predict_proba(stack.reshape(-1, c)[:, bundle["feature_indices"]])[:, 1]
    proba = proba.reshape(h, w)
    valid = valid_mask(chip)
    mask = ((proba >= float(bundle["threshold"])) & valid).astype(np.uint8)
    out = {
        "chip_id": chip_id,
        "model_version": AF_VERSION,
        "device": "cpu",
        "mask": mask,
        "probability": proba.astype(np.float32),
        "valid": valid,
        "threshold": float(bundle["threshold"]),
        "fire_pixels": int(mask.sum()),
        "runtime_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    gt = getattr(chip, "mask", None)
    if gt is not None:
        out["gt_mask"] = gt.astype(np.uint8)
        out["error_map"] = error_map(mask, gt.astype(np.uint8))
        out["error_map"][~valid] = 0
    return out


@lru_cache(maxsize=1)
def bs_models() -> dict:
    from kroma_ml.bs_v004 import load_thresholds

    return {
        "refiner": lgb.Booster(model_file=str(resolve("bs_v004_refiner"))),
        "component": lgb.Booster(model_file=str(resolve("bs_component"))),
        "refiner2": lgb.Booster(model_file=str(resolve("bs_refiner2"))),
        "thresholds": load_thresholds(resolve("bs_thresholds")),
    }


def bs_logits_subprocess(chip_ids: list[str], root: str, with_mask: bool) -> dict[str, np.ndarray]:
    global NEURAL_DEVICE
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, "-m", "kroma_ml.bs_neural", "--root", root, "--out-dir", tmp]
        if with_mask:
            cmd.append("--with-mask")
        subprocess.run([*cmd, *chip_ids], check=True, capture_output=True)
        NEURAL_DEVICE = json.loads((Path(tmp) / "runtime.json").read_text())["device"]
        return {cid: np.load(Path(tmp) / f"{cid}.npy") for cid in chip_ids}


def predict_bs(chip_id: str, root: str | None = None, logits: np.ndarray | None = None) -> dict:
    from kroma_ml.bs_crop import load_raw
    from kroma_ml.bs_physics import spectral_indices
    from kroma_ml.bs_rededge import RE_PIX, comp_stats, rededge_maps_root, ring_contrast
    from kroma_ml.bs_v004 import group_map, organizer_severity, pixel_features, threshold_map
    from kroma_ml.bs_v005 import compose_labels
    from kroma_ml.bs_v005_stages import FEATURES, chip_features, component_table, v004_test_maps

    started = time.perf_counter()
    root, has_gt = resolve_root(chip_id, "bs", root)
    raw = load_raw(chip_id, root=root, with_mask=has_gt)
    t_neural = time.perf_counter()
    if logits is None:
        logits = bs_logits_subprocess([chip_id], root, has_gt)[chip_id]
    neural_ms = (time.perf_counter() - t_neural) * 1000
    m = bs_models()
    th = m["thresholds"]
    t_refine = time.perf_counter()
    v4 = v004_test_maps(logits, pixel_features(raw, logits, th), m["refiner"])
    base, probs = v4["pred"].astype(np.int64), v4["probs"].astype(np.float32)
    dnbr = spectral_indices(raw.refl)["dnbr"]
    tmap = threshold_map(raw.landcover, th)
    org = organizer_severity(dnbr, tmap)
    lc = group_map(raw.landcover, th)
    valid = ~np.isin(raw.scl_pre, (0, 1)) & ~np.isin(raw.scl_post, (0, 1))
    lab, feats = component_table(1 - probs[0], base, dnbr, dnbr - tmap[0], org, lc, valid)
    rededge = rededge_maps_root(chip_id, root)
    extra = np.concatenate(
        [
            comp_stats(lab, [rededge[k] for k in RE_PIX[:7]]),
            np.stack(
                [ring_contrast(lab, rededge["dB5"]), ring_contrast(lab, rededge["dNDRE7"])], 1
            ).reshape(-1, 2),
        ],
        1,
    )
    feats = np.concatenate([feats, extra], 1)
    cp = np.concatenate([[1.0], m["component"].predict(feats) if len(feats) else []])[lab]
    f, zone = chip_features(raw, probs, base, th)
    sel = np.nonzero(zone.ravel())[0]
    r2 = np.zeros(base.size, np.float32)
    if len(sel):
        X = np.stack([np.asarray(f[n], np.float32).ravel()[sel] for n in FEATURES], 1)
        extra_pixels = np.stack([rededge[k].ravel()[sel] for k in RE_PIX], 1)
        X = X.astype(np.float16).astype(np.float32)
        extra_pixels = extra_pixels.astype(np.float16).astype(np.float32)
        r2[sel] = m["refiner2"].predict(np.concatenate([X, extra_pixels], 1))
    r2 = r2.reshape(base.shape)
    base_burn = base > 0
    removed = (lab > 0) & (cp < BS_RULE["comp_remove_below"])
    kept = base_burn & ~removed
    burn = (kept & ~(zone & (r2 < BS_RULE["refiner2_remove_below"]))) | (
        ~removed & zone & (r2 >= BS_RULE["refiner2_add_at_or_above"])
    )
    mask = np.where(burn & base_burn, base, compose_labels(burn, probs, org)).astype(np.uint8)
    burn_conf = np.where(zone, r2, 1 - probs[0]).astype(np.float32)
    burn_conf = np.where(removed, np.minimum(burn_conf, cp), burn_conf).astype(np.float32)
    areas = {
        name: round(float((mask == k).sum()) * PIXEL_HA, 2)
        for k, name in ((1, "low"), (2, "moderate"), (3, "high"))
    }
    out = {
        "chip_id": chip_id,
        "model_version": BS_VERSION,
        "device": NEURAL_DEVICE,
        "mask": mask,
        "burn_mask": (mask > 0).astype(np.uint8),
        "burn_probability": burn_conf,
        "severity_probability": probs[1:],
        "valid": valid,
        "total_burned_area_ha": round(float((mask > 0).sum()) * PIXEL_HA, 2),
        "area_ha": areas,
        "runtime_ms": {
            "total": round((time.perf_counter() - started) * 1000, 1),
            "neural": round(neural_ms, 1),
            "refine": round((time.perf_counter() - t_refine) * 1000, 1),
        },
    }
    if has_gt:
        gt = raw.mask.astype(np.uint8)
        out["gt_mask"] = gt
        out["error_map"] = error_map(mask, gt)
        out["error_map"][~valid | (gt == 255)] = 0
    return out


def error_map(pred: np.ndarray, gt: np.ndarray) -> np.ndarray:
    out = np.zeros(pred.shape, np.uint8)
    out[(pred > 0) & (gt == 0)] = 1
    out[(pred == 0) & (gt > 0)] = 2
    out[(pred > 0) & (gt > 0) & (pred != gt)] = 3
    return out


def summary(result: dict) -> dict:
    return {k: v for k, v in result.items() if not isinstance(v, np.ndarray)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("task", choices=("af", "bs", "status"))
    p.add_argument("chip_id", nargs="?")
    p.add_argument("--root", default=None)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    if args.task == "status":
        print(json.dumps(status(verify_hashes=True), indent=2, ensure_ascii=False))
        return
    if not args.chip_id:
        p.error("chip_id is required for af/bs")
    result = (
        predict_af(args.chip_id, args.root)
        if args.task == "af"
        else predict_bs(args.chip_id, args.root)
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            args.out, **{k: v for k, v in result.items() if isinstance(v, np.ndarray)}
        )
    print(json.dumps(summary(result), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
