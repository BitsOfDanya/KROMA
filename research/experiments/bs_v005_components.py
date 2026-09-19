import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_contour_diag import CROP, GRASS, V004_DIR, Tally
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, N_FOLDS, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map
from kroma_ml.bs_v005 import EIGHT, compose_labels
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_v005_components.json"
COMP_DIR = REPO / "data" / "processed" / "bs_v005" / "components"
CAND_T = 0.5
POS_OVERLAP = 0.5
SEED = 42
COMP_FEATURES = (
    "log_area", "perimeter_ratio", "compactness", "bbox_aspect", "fill_ratio",
    "p_mean", "p_max", "p_q90", "dnbr_mean", "dnbr_max", "dnbr_q90", "d_low_mean",
    "frac_sev2", "frac_sev3", "frac_org2", "frac_org3", "frac_crop", "frac_grass",
    "frac_forest", "frac_wet", "rank_area", "rank_sev3", "share_chip_burn",
    "dist_main_area", "dist_main_sev3", "n_components", "chip_burn_frac",
    "chip_dnbr_q90", "centroid_r", "touches_border", "ring_dnbr_mean", "ring_p_mean",
    "ring_org1_frac", "contrast_dnbr",
)  # fmt: skip


def component_table(p_burn, pred, dnbr, dlow, org, lc, valid, cand_t=CAND_T):
    cand = (p_burn >= cand_t) & valid
    lab, n = ndimage.label(cand, EIGHT)
    if not n:
        return lab, np.zeros((0, len(COMP_FEATURES)), np.float32)
    idx = np.arange(1, n + 1)
    area = ndimage.sum(np.ones_like(p_burn), lab, idx)
    edge = cand & ~ndimage.binary_erosion(cand, EIGHT)
    perim = ndimage.sum(edge, lab, idx)
    sl = ndimage.find_objects(lab)
    h = np.array([s[0].stop - s[0].start for s in sl], float)
    w = np.array([s[1].stop - s[1].start for s in sl], float)

    def mean(x):
        return ndimage.mean(x, lab, idx)

    def mx(x):
        return ndimage.maximum(x, lab, idx)

    def q90(x):
        return np.array([np.quantile(x[lab == i], 0.9) for i in idx]) if n <= 400 else mx(x)

    sev3 = ndimage.sum(pred == 3, lab, idx)
    yy, xx = np.mgrid[: lab.shape[0], : lab.shape[1]]
    cy, cx = mean(yy.astype(float)), mean(xx.astype(float))
    main_area = lab == idx[np.argmax(area)]
    main_sev3 = lab == idx[np.argmax(sev3 + 1e-3 * area)]
    d_area = ndimage.distance_transform_edt(~main_area)
    d_sev3 = ndimage.distance_transform_edt(~main_sev3)
    ring = ndimage.binary_dilation(cand, EIGHT, iterations=5) & ~cand
    ring_lab = ndimage.grey_dilation(lab, footprint=np.ones((11, 11)))
    ring_lab = np.where(ring, ring_lab, 0)
    ring_n = np.maximum(ndimage.sum(np.ones_like(p_burn), ring_lab, idx), 1)
    ring_dnbr = ndimage.sum(dnbr, ring_lab, idx) / ring_n
    border = np.zeros_like(cand)
    border[[0, -1], :] = border[:, [0, -1]] = True
    feats = np.stack(
        [
            np.log1p(area), perim / np.sqrt(area), 4 * np.pi * area / np.maximum(perim, 1) ** 2,
            np.maximum(h, w) / np.maximum(np.minimum(h, w), 1), area / (h * w),
            mean(p_burn), mx(p_burn), q90(p_burn), mean(dnbr), mx(dnbr), q90(dnbr), mean(dlow),
            mean((pred == 2).astype(float)), sev3 / area, mean((org == 2).astype(float)),
            mean((org == 3).astype(float)), mean((lc == 2).astype(float)),
            mean((lc == 1).astype(float)), mean((lc == 0).astype(float)), mean((lc == 3).astype(float)),
            (-area).argsort().argsort() / n, (-sev3).argsort().argsort() / n, area / area.sum(),
            ndimage.minimum(d_area, lab, idx), ndimage.minimum(d_sev3, lab, idx),
            np.full(n, np.log1p(n)), np.full(n, cand.mean()), np.full(n, np.quantile(dnbr[valid], 0.9)),
            np.hypot(cy - 255.5, cx - 255.5), ndimage.maximum(border, lab, idx).astype(float),
            ring_dnbr, ndimage.sum(p_burn, ring_lab, idx) / ring_n,
            ndimage.sum((org >= 1).astype(float), ring_lab, idx) / ring_n, mean(dnbr) - ring_dnbr,
        ],
        1,
    ).astype(np.float32)  # fmt: skip
    return lab, feats


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    COMP_DIR.mkdir(parents=True, exist_ok=True)
    folds = {}
    rows = {k: ([], [], []) for k in range(1, N_FOLDS + 1)}
    meta = load_meta()
    for cid in meta.chip_id:
        with np.load(V004_DIR / f"{cid}.npz") as z:
            pred, probs, k = (
                z["pred"].astype(np.int64),
                z["probs"].astype(np.float32),
                int(z["fold"]),
            )
        raw = load_raw(cid)
        gt = raw.mask.astype(np.int64)
        dnbr = spectral_indices(raw.refl)["dnbr"]
        tmap = threshold_map(raw.landcover, th)
        org = organizer_severity(dnbr, tmap)
        lc = group_map(raw.landcover, th)
        valid = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
        lab, feats = component_table(1 - probs[0], pred, dnbr, dnbr - tmap[0], org, lc, valid)
        n = feats.shape[0]
        overlap = (
            ndimage.mean((gt > 0).astype(float), lab, np.arange(1, n + 1)) if n else np.zeros(0)
        )
        area = ndimage.sum(np.ones_like(dnbr), lab, np.arange(1, n + 1)) if n else np.zeros(0)
        np.savez(COMP_DIR / f"{cid}.npz", lab=lab.astype(np.int32), feats=feats, overlap=overlap)
        rows[k][0].append(feats)
        rows[k][1].append((overlap >= POS_OVERLAP).astype(np.int64))
        rows[k][2].append(area)
        folds[cid] = k
    params = {
        "objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 20,
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
        "num_threads": 4, "seed": SEED, "verbose": -1, "deterministic": True,
    }  # fmt: skip
    comp_prob = {}
    auc = {}
    importance = np.zeros(len(COMP_FEATURES))
    for k in range(1, N_FOLDS + 1):
        X = np.concatenate([f for j in rows if j != k for f in rows[j][0]])
        y = np.concatenate([f for j in rows if j != k for f in rows[j][1]])
        w = np.log1p(np.concatenate([f for j in rows if j != k for f in rows[j][2]]))
        booster = lgb.train(
            params, lgb.Dataset(X, y, weight=w, feature_name=list(COMP_FEATURES)), 300
        )
        importance += booster.feature_importance("gain")
        Xv = np.concatenate(rows[k][0])
        yv = np.concatenate(rows[k][1])
        pv = booster.predict(Xv)
        order = np.argsort(pv)
        ranks = np.empty(len(pv))
        ranks[order] = np.arange(len(pv))
        pos = yv == 1
        auc[k] = float((ranks[pos].mean() - (pos.sum() - 1) / 2) / max((~pos).sum(), 1))
        for cid in (c for c in folds if folds[c] == k):
            with np.load(COMP_DIR / f"{cid}.npz") as z:
                comp_prob[cid] = booster.predict(z["feats"]) if len(z["feats"]) else np.zeros(0)
    tally = Tally()
    thresholds = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5)
    for cid, k in folds.items():
        with np.load(V004_DIR / f"{cid}.npz") as z:
            pred, probs = z["pred"].astype(np.int64), z["probs"].astype(np.float32)
        raw = load_raw(cid)
        gt = raw.mask.astype(np.int64)
        dnbr = spectral_indices(raw.refl)["dnbr"]
        org = organizer_severity(dnbr, threshold_map(raw.landcover, th))
        lc = group_map(raw.landcover, th)
        valids = {
            n: valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m) for n, m in EVAL_MODES.items()
        }
        va = valids["all_valid_mask"]
        masks = {**valids, "crop": va & (lc == CROP), "grass": va & (lc == GRASS)}
        lab = np.load(COMP_DIR / f"{cid}.npz")["lab"]
        cp = np.concatenate([[1.0], comp_prob[cid]])[lab]
        tally.add("v004", k, pred, gt, masks)
        for t in thresholds:
            kill = (lab > 0) & (cp < t)
            tally.add(f"comp_remove_p<{t}", k, np.where(kill, 0, pred), gt, masks)
            burn = (pred > 0) & ~kill
            tally.add(f"comp_remove_p<{t}_resev", k, compose_labels(burn, probs, org), gt, masks)
        np.save(COMP_DIR / f"{cid}_prob.npy", cp.astype(np.float16))
    summary = tally.summary()
    imp = dict(zip(COMP_FEATURES, (importance / importance.sum()).round(4).tolist(), strict=True))
    OUT_JSON.write_text(
        json.dumps({"auc": auc, "importance": imp, "variants": summary}, indent=2, default=float)
        + "\n"
    )
    print("component AUC per fold", {k: round(v, 3) for k, v in auc.items()})
    print("top features", sorted(imp.items(), key=lambda x: -x[1])[:12])
    base = summary["v004"]["all_valid_mask"]["bs_mean"]
    for name, e in summary.items():
        a = e["all_valid_mask"]
        print(
            f"{name:26s} all={a['bs_mean']:.4f} ({a['bs_mean'] - base:+.4f}) worst={a['bs_worst']:.4f} "
            f"folds={[round(v, 4) for v in a['per_fold'].values()]} strict={e['strict_mask']['bs_mean']:.4f} "
            f"burn={a['iou_burn']:.3f} iou1={a['iou'][1]:.3f} fp0b={a['fp_0toburn']:.4f} "
            f"fn10={a['fn_1to0']:.3f} crop={e['crop_fp_0toburn']:.4f} grass={e['grass_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
