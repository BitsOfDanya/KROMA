import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_components import COMP_DIR, COMP_FEATURES, component_table
from bs_v005_contour_diag import CROP, GRASS, V004_DIR, Tally
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, N_FOLDS, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import (
    group_map,
    load_thresholds,
    organizer_severity,
    signed_boundary_distance,
    threshold_map,
)
from kroma_ml.bs_v005 import clean_core, compose_labels, distance_to
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_v005_refiner2.json"
R2_DIR = REPO / "data" / "processed" / "bs_v005" / "refiner2"
SEED = 42
COMP05 = ("log_area", "dist_main_sev3", "share_chip_burn", "frac_sev3", "rank_sev3", "p_mean",
          "compactness", "ring_org1_frac", "contrast_dnbr", "dist_main_area", "rank_area")  # fmt: skip
COMP03 = ("log_area", "dist_main_sev3", "share_chip_burn", "p_mean", "frac_sev3")
PIX = (
    "p0", "p1", "p2", "p3", "p_burn", "pred", "dnbr", "rdnbr", "d_low", "d_mod", "org", "lc",
    "ndvi_post", "dndvi", "scl_pre", "scl_post",
    "dnbr_mean11", "dnbr_std11", "dnbr_mean41", "dnbr_std41", "pb_mean11", "pb_max11",
    "pb_mean41", "pb_max41", "org1_frac11", "org1_frac41", "dlow_min11", "samelc_frac41",
    "dist_boundary", "dist_main_sev3_px", "dist_main_area_px", "dist_core",
    "chip_burn_frac", "chip_n_comp", "chip_dnbr_q90",
)  # fmt: skip
FEATURES = PIX + tuple(f"c05_{n}" for n in COMP05) + tuple(f"c03_{n}" for n in COMP03)
CATEGORICAL = ("pred", "org", "lc", "scl_pre", "scl_post")
ZONE_P, ZONE_R = 0.15, 10.0
T_GRID = (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)


def local(x: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    m = ndimage.uniform_filter(x, size)
    return m, np.sqrt(np.maximum(ndimage.uniform_filter(x * x, size) - m * m, 0))


def comp_pixels(lab: np.ndarray, feats: np.ndarray, names: tuple) -> list[np.ndarray]:
    cols = [COMP_FEATURES.index(n) for n in names]
    table = (
        np.vstack([np.full((1, len(cols)), -1.0, np.float32), feats[:, cols]])
        if len(feats)
        else np.full((1, len(cols)), -1.0, np.float32)
    )
    return [table[lab, i] for i in range(len(cols))]


def chip_features(raw, probs, pred, th) -> tuple[dict, np.ndarray]:
    idx = spectral_indices(raw.refl)
    dnbr = idx["dnbr"]
    tmap = threshold_map(raw.landcover, th)
    org = organizer_severity(dnbr, tmap)
    lc = group_map(raw.landcover, th)
    valid = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
    p_burn = 1.0 - probs[0]
    lab5, f5 = component_table(p_burn, pred, dnbr, dnbr - tmap[0], org, lc, valid)
    lab3, f3 = component_table(p_burn, pred, dnbr, dnbr - tmap[0], org, lc, valid, cand_t=0.3)
    sev3 = ndimage.sum(pred == 3, lab5, np.arange(1, len(f5) + 1)) if len(f5) else np.zeros(0)
    area = (
        ndimage.sum(np.ones_like(dnbr), lab5, np.arange(1, len(f5) + 1)) if len(f5) else np.zeros(0)
    )
    if len(f5):
        main_sev3 = lab5 == 1 + int(np.argmax(sev3 + 1e-3 * area))
        main_area = lab5 == 1 + int(np.argmax(area))
    else:
        main_sev3 = main_area = np.zeros_like(valid)
    dm11, ds11 = local(dnbr, 11)
    dm41, ds41 = local(dnbr, 41)
    org1 = (org >= 1).astype(np.float32)
    same41 = np.zeros_like(dnbr)
    for g in range(4):
        frac = ndimage.uniform_filter((lc == g).astype(np.float32), 41)
        same41 = np.where(lc == g, frac, same41)
    f = {
        "p0": probs[0], "p1": probs[1], "p2": probs[2], "p3": probs[3], "p_burn": p_burn, "pred": pred,
        "dnbr": dnbr, "rdnbr": idx["rdnbr"], "d_low": dnbr - tmap[0], "d_mod": dnbr - tmap[1],
        "org": org, "lc": lc, "ndvi_post": idx["ndvi_post"], "dndvi": idx["dndvi"],
        "scl_pre": raw.scl_pre, "scl_post": raw.scl_post,
        "dnbr_mean11": dm11, "dnbr_std11": ds11, "dnbr_mean41": dm41, "dnbr_std41": ds41,
        "pb_mean11": ndimage.uniform_filter(p_burn, 11), "pb_max11": ndimage.maximum_filter(p_burn, 11),
        "pb_mean41": ndimage.uniform_filter(p_burn, 41), "pb_max41": ndimage.maximum_filter(p_burn, 41),
        "org1_frac11": ndimage.uniform_filter(org1, 11), "org1_frac41": ndimage.uniform_filter(org1, 41),
        "dlow_min11": ndimage.minimum_filter(dnbr - tmap[0], 11), "samelc_frac41": same41,
        "dist_boundary": signed_boundary_distance(pred > 0),
        "dist_main_sev3_px": distance_to(main_sev3), "dist_main_area_px": distance_to(main_area),
        "dist_core": distance_to(clean_core((p_burn >= 0.8) | (pred >= 2), 20)),
        "chip_burn_frac": np.full(dnbr.shape, (pred > 0).mean(), np.float32),
        "chip_n_comp": np.full(dnbr.shape, np.log1p(len(f5)), np.float32),
        "chip_dnbr_q90": np.full(dnbr.shape, np.quantile(dnbr[valid], 0.9) if valid.any() else 0, np.float32),
    }  # fmt: skip
    for n, v in zip(COMP05, comp_pixels(lab5, f5, COMP05), strict=True):
        f[f"c05_{n}"] = v
    for n, v in zip(COMP03, comp_pixels(lab3, f3, COMP03), strict=True):
        f[f"c03_{n}"] = v
    zone = ((p_burn >= ZONE_P) | (np.abs(f["dist_boundary"]) <= ZONE_R)) & valid
    return f, zone


def build(th) -> tuple[dict, dict]:
    R2_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    samples, index = {}, {}
    for cid in load_meta().chip_id:
        with np.load(V004_DIR / f"{cid}.npz") as z:
            pred, probs, k = (
                z["pred"].astype(np.int64),
                z["probs"].astype(np.float32),
                int(z["fold"]),
            )
        raw = load_raw(cid)
        gt = raw.mask.astype(np.int64)
        f, zone = chip_features(raw, probs, pred, th)
        sel = np.nonzero(zone.ravel())[0].astype(np.int32)
        X = np.stack([np.asarray(f[n], np.float32).ravel()[sel] for n in FEATURES], 1)
        y = (gt.ravel()[sel] > 0).astype(np.uint8)
        base = (pred.ravel()[sel] > 0).astype(np.uint8)
        c1 = gt.ravel()[sel] == 1
        bnd = np.abs(f["dist_boundary"].ravel()[sel]) <= 2
        parts = [rng.choice(len(y), min(len(y), 3000), replace=False)] if len(y) else []
        for m, cap in (
            ((y == 0) & (base == 1), 2500),
            ((y == 1) & (base == 0), 1500),
            (c1, 1500),
            (bnd, 1000),
        ):
            cand = np.nonzero(m)[0]
            if len(cand):
                parts.append(rng.choice(cand, min(len(cand), cap), replace=False))
        if parts:
            rows = np.unique(np.concatenate(parts))
            samples[cid] = (X[rows], y[rows])
        np.save(R2_DIR / f"{cid}_X.npy", X.astype(np.float16))
        np.save(R2_DIR / f"{cid}_sel.npy", sel)
        index[cid] = k
    return samples, index


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    samples, index = build(th)
    print("features built", flush=True)
    params = {
        "objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
        "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
        "num_threads": 4, "seed": SEED, "verbose": -1, "deterministic": True,
    }  # fmt: skip
    importance = np.zeros(len(FEATURES))
    for k in range(1, N_FOLDS + 1):
        parts = [v for c, v in samples.items() if index[c] != k]
        X = np.concatenate([p[0] for p in parts])
        y = np.concatenate([p[1] for p in parts])
        ds = lgb.Dataset(X, y, feature_name=list(FEATURES), categorical_feature=list(CATEGORICAL))
        booster = lgb.train(params, ds, 500)
        booster.save_model(str(R2_DIR / f"refiner2_oof_f{k}.txt"))
        importance += booster.feature_importance("gain")
        for c in (c for c in index if index[c] == k):
            X = np.load(R2_DIR / f"{c}_X.npy").astype(np.float32)
            np.save(
                R2_DIR / f"{c}_p.npy",
                (booster.predict(X) if len(X) else np.zeros(0)).astype(np.float16),
            )
        print(f"fold {k} trained rows={len(y)} pos={y.mean():.3f}", flush=True)
    tally = Tally()
    for cid, k in index.items():
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
        sel = np.load(R2_DIR / f"{cid}_sel.npy")
        pr = np.load(R2_DIR / f"{cid}_p.npy").astype(np.float32)
        tally.add("v004", k, pred, gt, masks)
        lab = np.load(COMP_DIR / f"{cid}.npz")["lab"]
        comp_p = np.load(COMP_DIR / f"{cid}_prob.npy").astype(np.float32)
        tally.add("v005a_comp_p<0.3", k, np.where((lab > 0) & (comp_p < 0.3), 0, pred), gt, masks)
        for t in T_GRID:
            burn = pred > 0
            flat = burn.ravel().copy()
            flat[sel] = pr >= t
            burn = flat.reshape(burn.shape)
            keep_sev = np.where(burn & (pred > 0), pred, compose_labels(burn, probs, org))
            tally.add(f"refiner2_t{t}", k, keep_sev, gt, masks)
    summary = tally.summary()
    imp = dict(zip(FEATURES, (importance / importance.sum()).round(4).tolist(), strict=True))
    OUT_JSON.write_text(
        json.dumps({"importance": imp, "variants": summary}, indent=2, default=float) + "\n"
    )
    print("top features", sorted(imp.items(), key=lambda x: -x[1])[:15])
    base = summary["v004"]["all_valid_mask"]["bs_mean"]
    for name, e in summary.items():
        a = e["all_valid_mask"]
        print(
            f"{name:20s} all={a['bs_mean']:.4f} ({a['bs_mean'] - base:+.4f}) worst={a['bs_worst']:.4f} "
            f"folds={[round(v, 4) for v in a['per_fold'].values()]} strict={e['strict_mask']['bs_mean']:.4f} "
            f"burn={a['iou_burn']:.3f} iou={[round(x, 3) for x in a['iou']]} fp0b={a['fp_0toburn']:.4f} "
            f"fn10={a['fn_1to0']:.3f} crop={e['crop_fp_0toburn']:.4f} grass={e['grass_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
