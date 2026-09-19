import argparse
import hashlib
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from bs_v004_fasttrack import THRESHOLDS
from bs_v004_logits import LOGITS_DIR
from bs_v005_components import COMP_DIR, component_table
from bs_v005_contour_diag import V004_DIR
from bs_v005_infer import V004_BS, V004_REFINER, train_component_model, v004_test_maps
from bs_v005_refiner2 import CATEGORICAL, FEATURES, R2_DIR, SEED, chip_features
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import (
    group_map,
    load_thresholds,
    organizer_severity,
    pixel_features,
    threshold_map,
)
from kroma_ml.bs_v005 import compose_labels
from kroma_ml.submission import multiclass_to_binary_rles

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "artifacts"


def train_full_refiner2(path: Path) -> lgb.Booster:
    rng = np.random.default_rng(SEED)
    xs, ys = [], []
    for cid in load_meta().chip_id:
        X = np.load(R2_DIR / f"{cid}_X.npy").astype(np.float32)
        sel = np.load(R2_DIR / f"{cid}_sel.npy")
        if not len(sel):
            continue
        gt = load_raw(cid).mask.ravel()[sel]
        pred = np.load(V004_DIR / f"{cid}.npz")["pred"].ravel()[sel]
        y = (gt > 0).astype(np.uint8)
        base = (pred > 0).astype(np.uint8)
        bnd = np.abs(X[:, FEATURES.index("dist_boundary")]) <= 2
        parts = [rng.choice(len(y), min(len(y), 3000), replace=False)]
        for m, cap in (
            ((y == 0) & (base == 1), 2500),
            ((y == 1) & (base == 0), 1500),
            (gt == 1, 1500),
            (bnd, 1000),
        ):
            cand = np.nonzero(m)[0]
            if len(cand):
                parts.append(rng.choice(cand, min(len(cand), cap), replace=False))
        rows = np.unique(np.concatenate(parts))
        xs.append(X[rows])
        ys.append(y[rows])
    params = {
        "objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
        "num_threads": 4, "seed": SEED, "verbose": -1, "deterministic": True,
    }  # fmt: skip
    ds = lgb.Dataset(np.concatenate(xs), np.concatenate(ys), feature_name=list(FEATURES),
                     categorical_feature=list(CATEGORICAL))  # fmt: skip
    booster = lgb.train(params, ds, 500)
    booster.save_model(str(path))
    return booster


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="v005b_candidate")
    p.add_argument("--comp-t", type=float, default=0.3)
    p.add_argument("--add-t", type=float, default=0.8)
    p.add_argument("--rm-t", type=float, default=0.2)
    args = p.parse_args()
    th = load_thresholds(THRESHOLDS)
    refiner = lgb.Booster(model_file=str(V004_REFINER))
    comp_model = train_component_model(COMP_DIR / f"component_full_{args.tag}.txt")
    r2_model = train_full_refiner2(R2_DIR / f"refiner2_full_{args.tag}.txt")
    v004_rows = pd.read_csv(V004_BS, keep_default_na=False).set_index(["chip_id", "class_id"])[
        "rle"
    ]
    meta = pd.read_csv(REPO / "data/test/meta.csv")
    ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()
    rows, stats, digests, mismatch = [], [], [], []
    started = time.perf_counter()
    for cid in ids:
        raw = load_raw(cid, root=str(REPO / "data/test/bs"), with_mask=False)
        t0 = time.perf_counter()
        logits = np.load(LOGITS_DIR / f"{cid}.npy")
        m = v004_test_maps(logits, pixel_features(raw, logits, th), refiner)
        base = m["pred"].astype(np.int64)
        probs = m["probs"].astype(np.float32)
        rl = multiclass_to_binary_rles(base.astype(np.uint8), (1, 2, 3))
        if any(rl[k] != v004_rows[(cid, k)] for k in (1, 2, 3)):
            mismatch.append(cid)
        t1 = time.perf_counter()
        dnbr = spectral_indices(raw.refl)["dnbr"]
        tmap = threshold_map(raw.landcover, th)
        org = organizer_severity(dnbr, tmap)
        lc = group_map(raw.landcover, th)
        valid = ~np.isin(raw.scl_pre, (0, 1)) & ~np.isin(raw.scl_post, (0, 1))
        lab, feats = component_table(1 - probs[0], base, dnbr, dnbr - tmap[0], org, lc, valid)
        cp = np.concatenate([[1.0], comp_model.predict(feats) if len(feats) else []])[lab]
        f, zone = chip_features(raw, probs, base, th)
        sel = np.nonzero(zone.ravel())[0]
        r2 = np.zeros(base.size, np.float32)
        if len(sel):
            X = np.stack([np.asarray(f[n], np.float32).ravel()[sel] for n in FEATURES], 1)
            r2[sel] = r2_model.predict(X.astype(np.float16).astype(np.float32))
        r2 = r2.reshape(base.shape)
        in_zone = zone
        base_burn = base > 0
        removed = (lab > 0) & (cp < args.comp_t)
        kept = base_burn & ~removed
        burn = (kept & ~(in_zone & (r2 < args.rm_t))) | (~removed & in_zone & (r2 >= args.add_t))
        pred = np.where(burn & base_burn, base, compose_labels(burn, probs, org)).astype(np.uint8)
        post_ms = (time.perf_counter() - t1) * 1000
        rles = multiclass_to_binary_rles(pred, (1, 2, 3))
        rows += [(cid, k, rles[k]) for k in (1, 2, 3)]
        digests.append(hashlib.sha256(pred.tobytes()).hexdigest())
        stats.append(
            {
                "chip_id": cid,
                "ms_total": (time.perf_counter() - t0) * 1000,
                "ms_contour_stage": post_ms,
                "removed_px": int((base_burn & ~burn).sum()),
                "added_px": int((~base_burn & burn).sum()),
                "base_burn_px": int(base_burn.sum()),
                **{f"sev{k}_px": int((pred == k).sum()) for k in (1, 2, 3)},
            }
        )
    if mismatch:
        raise RuntimeError(f"v004 reconstruction differs from submission for {mismatch[:5]}")
    out = ARTIFACTS / f"bs_submission_{args.tag}.csv"
    pd.DataFrame(rows, columns=["chip_id", "class_id", "rle"]).to_csv(out, index=False)
    chips = pd.DataFrame(stats)
    manifest = {
        "base": "v004 (reproduced byte-exactly on all BS test chips before post-processing)",
        "component_model": str((COMP_DIR / f"component_full_{args.tag}.txt").relative_to(REPO)),
        "refiner2_model": str((R2_DIR / f"refiner2_full_{args.tag}.txt").relative_to(REPO)),
        "rule": {
            "comp_remove_below": args.comp_t,
            "refiner2_add_at_or_above": args.add_t,
            "refiner2_remove_below": args.rm_t,
        },
        "bs_chips": len(ids),
        "removed_burn_share_test": float(chips.removed_px.sum() / max(chips.base_burn_px.sum(), 1)),
        "added_burn_share_test": float(chips.added_px.sum() / max(chips.base_burn_px.sum(), 1)),
        "mean_ms_per_chip": round(float(chips.ms_total.mean()), 1),
        "mean_ms_contour_stage": round(float(chips.ms_contour_stage.mean()), 1),
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
