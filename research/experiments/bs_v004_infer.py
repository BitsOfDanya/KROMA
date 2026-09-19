import argparse
import hashlib
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from bs_v004_fasttrack import (
    CATEGORICAL,
    FEATURES,
    OUT_DIR,
    SEED,
    THRESHOLDS,
    WIDE,
    gt_boundary01,
    hybrids,
    sample_rows,
)
from bs_v004_logits import LOGITS_DIR
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_metrics import NUM_CLASSES
from kroma_ml.bs_v004 import V003_BIAS, load_thresholds, pixel_features, refine_gate, stack
from kroma_ml.submission import multiclass_to_binary_rles

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "artifacts"
V003_MEMBERS = (
    REPO / "research/experiments/bs_full_ndvi_ohem40.pt",
    REPO / "research/experiments/bs_full_dual.pt",
)
V003_BS = ARTIFACTS / "bs_submission_v003.csv"


def train_full_refiner(path: Path) -> lgb.Booster:
    rng = np.random.default_rng(SEED)
    xs, ys = [], []
    for f in sorted((OUT_DIR / "chips").glob("BS_tr_*[0-9].npz")):
        with np.load(f) as d:
            if not len(d["y"]):
                continue
            gt = d["gt"].astype(np.int64)
            bnd = gt_boundary01(gt).ravel()[d["sel"]]
            rows = sample_rows(d["y"], d["base"].ravel()[d["sel"]], bnd, rng)
            xs.append(d["X"][rows])
            ys.append(d["y"][rows])
    X, y = np.concatenate(xs), np.concatenate(ys).astype(np.int64)
    ds = lgb.Dataset(X, y, feature_name=list(FEATURES), categorical_feature=list(CATEGORICAL))
    params = {
        "objective": "multiclass", "num_class": NUM_CLASSES, "learning_rate": 0.05,
        "num_leaves": 63, "min_data_in_leaf": 200, "feature_fraction": 0.8,
        "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
        "num_threads": 4, "seed": SEED, "verbose": -1, "deterministic": True,
    }  # fmt: skip
    booster = lgb.train(params, ds, num_boost_round=400)
    booster.save_model(str(path))
    return booster


def refine(pred, f, booster, band, radius, bias) -> np.ndarray:
    wide = refine_gate(f, WIDE["band"], WIDE["radius"], WIDE["keep_conf"])
    sel = np.nonzero(wide.ravel())[0]
    if not len(sel):
        return pred
    X = stack(f, wide)
    logp = np.log(np.maximum(booster.predict(X), 1e-9)) + np.asarray(bias)
    p_burn, dist = f["p_burn"].ravel()[sel], f["dist_pred_boundary"].ravel()[sel]
    gate = (p_burn >= band) & (p_burn <= 1 - band)
    if radius >= 0:
        gate |= np.abs(dist) <= radius
    out = pred.ravel().copy()
    out[sel[gate]] = logp[gate].argmax(1)
    return out.reshape(pred.shape)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v004")
    p.add_argument("--hybrid", default="", help="variant name from bs_v004_fasttrack.hybrids")
    p.add_argument("--refiner", action="store_true")
    p.add_argument("--band", type=float, default=0.2)
    p.add_argument("--radius", type=float, default=2.0)
    p.add_argument("--bias", default="0,0,0,0")
    args = p.parse_args()
    meta = pd.read_csv(REPO / "data/test/meta.csv")
    ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()
    th = load_thresholds(THRESHOLDS)
    booster = None
    if args.refiner:
        booster = train_full_refiner(OUT_DIR / f"refiner_full_{args.tag}.txt")
    bias = [float(x) for x in args.bias.split(",")]
    rows, stats, digests = [], [], []
    started = time.perf_counter()
    for cid in ids:
        raw = load_raw(cid, root=str(REPO / "data/test/bs"), with_mask=False)
        t0 = time.perf_counter()
        logits = np.load(LOGITS_DIR / f"{cid}.npy")
        base = logits.argmax(0).astype(np.uint8)
        f = pixel_features(raw, logits, th)
        pred = base.astype(np.int64)
        if booster is not None:
            pred = refine(pred, f, booster, args.band, args.radius, bias)
            f = {**f, "pred": pred, "p_burn": f["p_burn"]}
        if args.hybrid:
            pred = hybrids(f, logits)[args.hybrid]
        pred = pred.astype(np.uint8)
        ms = (time.perf_counter() - t0) * 1000
        rles = multiclass_to_binary_rles(pred, (1, 2, 3))
        rows += [(cid, k, rles[k]) for k in (1, 2, 3)]
        digests.append(hashlib.sha256(pred.tobytes()).hexdigest())
        stats.append(
            {
                "chip_id": cid,
                "ms": ms,
                "changed_px": int((pred != base).sum()),
                **{f"sev{k}_px": int((pred == k).sum()) for k in (1, 2, 3)},
            }
        )
    out = ARTIFACTS / f"bs_submission_{args.tag}.csv"
    pd.DataFrame(rows, columns=["chip_id", "class_id", "rle"]).to_csv(out, index=False)
    chips = pd.DataFrame(stats)
    manifest = {
        "base": "v003 full-train ensemble (read-only), byte-exact before post-processing",
        "members": [str(m.relative_to(REPO)) for m in V003_MEMBERS],
        "members_sha256": [hashlib.sha256(m.read_bytes()).hexdigest() for m in V003_MEMBERS],
        "v003_bias": V003_BIAS.tolist(),
        "hybrid": args.hybrid or None,
        "refiner": bool(args.refiner),
        "refiner_gate": {"band": args.band, "radius": args.radius} if args.refiner else None,
        "refiner_bias": bias if args.refiner else None,
        "thresholds": str(THRESHOLDS.relative_to(REPO)),
        "bs_chips": len(ids),
        "changed_px_share": float(chips.changed_px.sum() / (len(ids) * 512 * 512)),
        "mean_ms_per_chip": round(float(chips.ms.mean()), 1),
        "total_seconds": round(time.perf_counter() - started, 1),
        "total_sev_px": {k: int(chips[f"sev{k}_px"].sum()) for k in (1, 2, 3)},
        "deterministic_sha256": hashlib.sha256("".join(digests).encode()).hexdigest(),
        "submission": str(out.relative_to(REPO)),
    }
    (ARTIFACTS / f"bs_test_manifest_{args.tag}.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
