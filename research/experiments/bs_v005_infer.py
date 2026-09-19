import argparse
import hashlib
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from bs_v004_fasttrack import OUT_DIR as V004_OUT
from bs_v004_fasttrack import THRESHOLDS, WIDE, hybrids
from bs_v004_logits import LOGITS_DIR
from bs_v005_components import COMP_DIR, COMP_FEATURES, POS_OVERLAP, SEED, component_table
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import (
    group_map,
    load_thresholds,
    organizer_severity,
    pixel_features,
    refine_gate,
    softmax,
    stack,
    threshold_map,
)
from kroma_ml.submission import multiclass_to_binary_rles

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "artifacts"
CANDIDATES = ARTIFACTS / "submissions" / "candidates"
V004_REFINER = V004_OUT / "refiner_full_v004.txt"
V004_BS = ARTIFACTS / "bs_submission_v004.csv"
V004_BIAS = np.array([0.0, 0.4, 1.0, 0.8], dtype=np.float32)
BAND, RADIUS = 0.3, 2.0


def v004_test_maps(logits: np.ndarray, f: dict, refiner: lgb.Booster) -> dict:
    probs = softmax(logits)
    wide = refine_gate(f, WIDE["band"], WIDE["radius"], WIDE["keep_conf"])
    sel = np.nonzero(wide.ravel())[0]
    flat = probs.reshape(4, -1).copy()
    if len(sel):
        logp = np.log(np.maximum(refiner.predict(stack(f, wide)), 1e-9)) + V004_BIAS
        p_burn, dist = f["p_burn"].ravel()[sel], f["dist_pred_boundary"].ravel()[sel]
        gate = (p_burn >= BAND) & (p_burn <= 1 - BAND) | (np.abs(dist) <= RADIUS)
        refined = np.exp(logp[gate])
        flat[:, sel[gate]] = (refined / refined.sum(1, keepdims=True)).T
    probs = flat.reshape(probs.shape)
    pred = probs.argmax(0)
    final = hybrids({**f, "pred": pred}, logits)["hybrid_C_w1.0"]
    return {"probs": probs, "pred": final}


def train_component_model(path: Path) -> lgb.Booster:
    xs, ys, ws = [], [], []
    for cid in load_meta().chip_id:
        with np.load(COMP_DIR / f"{cid}.npz") as z:
            if not len(z["feats"]):
                continue
            area = np.bincount(z["lab"].ravel())[1:]
            xs.append(z["feats"])
            ys.append((z["overlap"] >= POS_OVERLAP).astype(np.int64))
            ws.append(np.log1p(area))
    params = {
        "objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 20,
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
        "num_threads": 4, "seed": SEED, "verbose": -1, "deterministic": True,
    }  # fmt: skip
    ds = lgb.Dataset(np.concatenate(xs), np.concatenate(ys), weight=np.concatenate(ws),
                     feature_name=list(COMP_FEATURES))  # fmt: skip
    booster = lgb.train(params, ds, 300)
    booster.save_model(str(path))
    return booster


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v005_candidate")
    p.add_argument("--comp-threshold", type=float, default=0.3)
    args = p.parse_args()
    th = load_thresholds(THRESHOLDS)
    refiner = lgb.Booster(model_file=str(V004_REFINER))
    comp_model = train_component_model(COMP_DIR / f"component_full_{args.tag}.txt")
    v004_rows = pd.read_csv(V004_BS, keep_default_na=False).set_index(["chip_id", "class_id"])[
        "rle"
    ]
    meta = pd.read_csv(REPO / "data/test/meta.csv")
    ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()
    rows, stats, digests, mismatch, feat_rows = [], [], [], [], []
    started = time.perf_counter()
    for cid in ids:
        raw = load_raw(cid, root=str(REPO / "data/test/bs"), with_mask=False)
        t0 = time.perf_counter()
        logits = np.load(LOGITS_DIR / f"{cid}.npy")
        f = pixel_features(raw, logits, th)
        m = v004_test_maps(logits, f, refiner)
        base = m["pred"].astype(np.uint8)
        base_rles = multiclass_to_binary_rles(base, (1, 2, 3))
        if any(base_rles[k] != v004_rows[(cid, k)] for k in (1, 2, 3)):
            mismatch.append(cid)
        t1 = time.perf_counter()
        dnbr = spectral_indices(raw.refl)["dnbr"]
        tmap = threshold_map(raw.landcover, th)
        org = organizer_severity(dnbr, tmap)
        lc = group_map(raw.landcover, th)
        valid = ~np.isin(raw.scl_pre, (0, 1)) & ~np.isin(raw.scl_post, (0, 1))
        lab, feats = component_table(
            1 - m["probs"][0], base.astype(np.int64), dnbr, dnbr - tmap[0], org, lc, valid
        )
        cp = np.concatenate([[1.0], comp_model.predict(feats) if len(feats) else []])[lab]
        pred = np.where((lab > 0) & (cp < args.comp_threshold), 0, base).astype(np.uint8)
        comp_ms = (time.perf_counter() - t1) * 1000
        if len(feats):
            feat_rows.append(feats)
        rles = multiclass_to_binary_rles(pred, (1, 2, 3))
        rows += [(cid, k, rles[k]) for k in (1, 2, 3)]
        digests.append(hashlib.sha256(pred.tobytes()).hexdigest())
        stats.append(
            {
                "chip_id": cid,
                "ms_total": (time.perf_counter() - t0) * 1000,
                "ms_components": comp_ms,
                "removed_px": int(((pred == 0) & (base > 0)).sum()),
                "base_burn_px": int((base > 0).sum()),
                **{f"sev{k}_px": int((pred == k).sum()) for k in (1, 2, 3)},
            }
        )
    if mismatch:
        raise RuntimeError(f"v004 reconstruction differs from submission for {mismatch[:5]}")
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    out = ARTIFACTS / f"bs_submission_{args.tag}.csv"
    pd.DataFrame(rows, columns=["chip_id", "class_id", "rle"]).to_csv(out, index=False)
    chips = pd.DataFrame(stats)
    test_feats = np.concatenate(feat_rows)
    oof_feats = np.concatenate(
        [np.load(COMP_DIR / f"{c}.npz")["feats"] for c in load_meta().chip_id]
    )
    shift = {
        name: {
            "oof_median": float(np.median(oof_feats[:, i])),
            "test_median": float(np.median(test_feats[:, i])),
        }
        for i, name in enumerate(COMP_FEATURES)
    }
    manifest = {
        "base": "v004 (reproduced byte-exactly on all BS test chips before post-processing)",
        "component_model": str((COMP_DIR / f"component_full_{args.tag}.txt").relative_to(REPO)),
        "component_threshold": args.comp_threshold,
        "component_candidate_p_burn": 0.5,
        "bs_chips": len(ids),
        "removed_burn_share_test": float(chips.removed_px.sum() / max(chips.base_burn_px.sum(), 1)),
        "mean_ms_per_chip": round(float(chips.ms_total.mean()), 1),
        "mean_ms_components": round(float(chips.ms_components.mean()), 1),
        "total_seconds": round(time.perf_counter() - started, 1),
        "total_sev_px": {k: int(chips[f"sev{k}_px"].sum()) for k in (1, 2, 3)},
        "deterministic_sha256": hashlib.sha256("".join(digests).encode()).hexdigest(),
        "feature_shift_oof_vs_test": shift,
        "submission": str(out.relative_to(REPO)),
    }
    (ARTIFACTS / f"bs_test_manifest_{args.tag}.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(
        json.dumps(
            {k: v for k, v in manifest.items() if k != "feature_shift_oof_vs_test"}, indent=2
        )
    )
    for name in (
        "dist_main_sev3",
        "chip_burn_frac",
        "n_components",
        "p_mean",
        "log_area",
        "share_chip_burn",
    ):
        print(name, shift[name])


if __name__ == "__main__":
    main()
