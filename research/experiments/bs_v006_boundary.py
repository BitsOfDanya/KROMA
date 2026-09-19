import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_components import COMP_DIR
from bs_v005_contour_diag import CROP, GRASS, V004_DIR, Tally
from bs_v005_refiner2 import FEATURES, R2_DIR
from bs_v006_prep import V006
from bs_v006_stack import EXTRA, RE_PIX
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, N_FOLDS, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map
from kroma_ml.bs_v005 import compose_labels
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
STACK_C = V006 / "stack_C"
OUT_JSON = REPO / "research" / "experiments" / "bs_v006_boundary.json"
RULE = (0.3, 0.8, 0.2)
BAND = 3
SEED = 42
NEW = ("c_r2", "c_comp", "c_dist", "c_frac3", "c_frac5", "c_frac7", "c_burn", "v005_burn_changed")
NAMES = list(FEATURES) + list(RE_PIX) + list(NEW)
PARAMS = {
    "objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "num_threads": 6, "seed": SEED, "verbose": -1, "deterministic": True,
}  # fmt: skip
T_GRID = (0.4, 0.45, 0.5, 0.55, 0.6)


def chip_state(cid: str) -> dict:
    with np.load(V004_DIR / f"{cid}.npz") as z:
        pred, probs, k = z["pred"].astype(np.int64), z["probs"].astype(np.float32), int(z["fold"])
    lab = np.load(COMP_DIR / f"{cid}.npz")["lab"]
    cp = np.concatenate([[1.0], np.load(STACK_C / f"{cid}_comp.npy")])[lab]
    sel = np.load(R2_DIR / f"{cid}_sel.npy")
    r2 = np.zeros(pred.size, np.float32)
    r2[sel] = np.load(STACK_C / f"{cid}_pix.npy")
    zone = np.zeros(pred.size, bool)
    zone[sel] = True
    r2, zone = r2.reshape(pred.shape), zone.reshape(pred.shape)
    base = pred > 0
    removed = (lab > 0) & (cp < RULE[0])
    burn = (base & ~removed & ~(zone & (r2 < RULE[2]))) | (~removed & zone & (r2 >= RULE[1]))
    out_d = ndimage.distance_transform_edt(~burn) if burn.any() else np.full(burn.shape, 99.0)
    in_d = ndimage.distance_transform_edt(burn) if burn.any() else np.zeros(burn.shape)
    sdist = np.where(burn, in_d, -out_d).astype(np.float32)
    band = (np.abs(sdist) <= BAND) & zone
    b = burn.astype(np.float32)
    maps = {
        "c_r2": r2, "c_comp": cp.astype(np.float32), "c_dist": sdist,
        "c_frac3": ndimage.uniform_filter(b, 3), "c_frac5": ndimage.uniform_filter(b, 5),
        "c_frac7": ndimage.uniform_filter(b, 7), "c_burn": b,
        "v005_burn_changed": (burn != base).astype(np.float32),
    }  # fmt: skip
    return {
        "pred": pred,
        "probs": probs,
        "fold": k,
        "burn": burn,
        "band": band,
        "sel": sel,
        "maps": maps,
    }


def band_matrix(cid: str, st: dict) -> tuple[np.ndarray, np.ndarray]:
    X = np.load(R2_DIR / f"{cid}_X.npy").astype(np.float32)
    re = np.load(EXTRA / f"{cid}_re_pix.npy").astype(np.float32)
    pos = np.full(st["pred"].size, -1, np.int64)
    pos[st["sel"]] = np.arange(len(st["sel"]))
    idx = np.nonzero(st["band"].ravel())[0]
    rows = pos[idx]
    extra = np.stack([st["maps"][n].ravel()[idx] for n in NEW], 1)
    return np.concatenate([X[rows], re[rows], extra], 1), idx


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    meta = load_meta()
    rng = np.random.default_rng(SEED)
    samples, states = {}, {}
    for cid in meta.chip_id:
        st = chip_state(cid)
        Xb, idx = band_matrix(cid, st)
        gt = load_raw(cid).mask.ravel()[idx]
        y = (gt > 0).astype(np.uint8)
        take = rng.choice(len(y), min(len(y), 6000), replace=False) if len(y) else np.zeros(0, int)
        samples[cid] = (Xb[take], y[take], st["fold"])
        states[cid] = st["fold"]
    probs_band = {}
    for k in range(1, N_FOLDS + 1):
        X = np.concatenate([s[0] for s in samples.values() if s[2] != k])
        y = np.concatenate([s[1] for s in samples.values() if s[2] != k])
        booster = lgb.train(PARAMS, lgb.Dataset(X, y, feature_name=NAMES), 400)
        booster.save_model(str(V006 / f"boundary_oof_f{k}.txt"))
        for cid in (c for c in meta.chip_id if states[c] == k):
            st = chip_state(cid)
            Xb, idx = band_matrix(cid, st)
            probs_band[cid] = (idx, booster.predict(Xb) if len(idx) else np.zeros(0))
        print(f"fold {k} boundary model trained rows={len(y)}", flush=True)
    tally = Tally()
    for cid in meta.chip_id:
        st = chip_state(cid)
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
        pred, probs, burn = st["pred"], st["probs"], st["burn"]
        lblC = np.where(burn & (pred > 0), pred, compose_labels(burn, probs, org))
        tally.add("C_redge", st["fold"], lblC, gt, masks)
        idx, pb = probs_band[cid]
        for t in T_GRID:
            nb = burn.ravel().copy()
            nb[idx] = pb >= t
            nb = nb.reshape(burn.shape)
            lbl = np.where(nb & burn, lblC, compose_labels(nb, probs, org))
            tally.add(f"C_boundary_t{t}", st["fold"], lbl, gt, masks)
            only_add = burn | nb
            lbl2 = np.where(only_add & burn, lblC, compose_labels(only_add, probs, org))
            tally.add(f"C_boundary_addonly_t{t}", st["fold"], lbl2, gt, masks)
    summary = tally.summary()
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=float) + "\n")
    for name, e in sorted(summary.items(), key=lambda x: -x[1]["all_valid_mask"]["bs_mean"]):
        a = e["all_valid_mask"]
        print(
            f"{name:26s} all={a['bs_mean']:.4f} folds={[round(v, 4) for v in a['per_fold'].values()]} "
            f"strict={e['strict_mask']['bs_mean']:.4f} burn={a['iou_burn']:.3f} "
            f"iou={[round(x, 3) for x in a['iou']]} fp01={a['fp_0to1']:.4f} fn10={a['fn_1to0']:.3f} "
            f"crop={e['crop_fp_0toburn']:.4f} grass={e['grass_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
