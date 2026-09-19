import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import (
    EVAL_MODES,
    N_FOLDS,
    confusion,
    fold_of,
    metrics_from_confusion,
    valid_mask,
)
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_metrics import NUM_CLASSES
from kroma_ml.bs_v004 import (
    CATEGORICAL,
    FEATURES,
    GROUP_ORDER,
    load_thresholds,
    pixel_features,
    refine_gate,
    stack,
    v003_logits,
)
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
EXP = REPO / "research" / "experiments"
THRESHOLDS = EXP / "bs_v004_physics_thresholds.json"
OOF_DIR = Path(os.environ.get("KROMA_V003_OOF_DIR", "/tmp/bs_oof"))
OUT_JSON = EXP / "bs_v004_fasttrack_results.json"
OUT_DIR = REPO / "data" / "processed" / "bs_v004"
B_TAUS = (0.5, 0.6, 0.7, 0.8, 0.9)
C_WEIGHTS = (0.25, 0.5, 1.0, 2.0)
WIDE = {"band": 0.03, "radius": 6.0, "keep_conf": 0.6}
GATES = {
    "wide": (0.03, 6.0),
    "band10_r4": (0.10, 4.0),
    "band10_r0": (0.10, -1.0),
    "band20_r2": (0.20, 2.0),
}
CROP = GROUP_ORDER.index("cropland")
SEED = 42


def zero_cm() -> np.ndarray:
    return np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)


class Tally:
    def __init__(self) -> None:
        self.cm: dict = {}

    def add(self, variant: str, key: str, fold: int, cm: np.ndarray) -> None:
        self.cm.setdefault(variant, {}).setdefault(key, {}).setdefault(fold, zero_cm())
        self.cm[variant][key][fold] += cm

    def record(self, variant: str, fold: int, pred, chip: dict) -> None:
        for name, v in chip["valids"].items():
            self.add(variant, name, fold, confusion(pred, chip["gt"], v))
        self.add(variant, "crop_all_valid", fold, confusion(pred, chip["gt"], chip["crop"]))
        self.add(variant, "crop_weak_dnbr", fold, confusion(pred, chip["gt"], chip["crop_weak"]))


def summarize(t: Tally) -> dict:
    out = {}
    for variant, keys in t.cm.items():
        entry = {}
        for name in EVAL_MODES:
            folds = keys[name]
            per = {k: metrics_from_confusion(cm)["bs_score"] for k, cm in folds.items()}
            pooled = metrics_from_confusion(sum(folds.values()))
            entry[name] = {
                "bs_mean": float(np.mean(list(per.values()))),
                "bs_worst": float(min(per.values())),
                "per_fold": per,
                "pooled": pooled,
                "fp_0to1": pooled["row_normalized"][0][1],
                "fn_1to0": pooled["row_normalized"][1][0],
            }
        for key in ("crop_all_valid", "crop_weak_dnbr"):
            cm = sum(keys[key].values())
            entry[key + "_fp_0to1"] = float(cm[0, 1] / max(cm[0].sum(), 1))
            entry[key + "_fp_0toburn"] = float(cm[0, 1:].sum() / max(cm[0].sum(), 1))
        out[variant] = entry
    return out


def hybrids(f: dict, logits: np.ndarray) -> dict[str, np.ndarray]:
    pred = f["pred"]
    burn = pred > 0
    org = np.clip(f["org_sev"], 1, 3)
    out = {"hybrid_A": np.where(burn, org, 0)}
    sev_p = np.stack([f["p1"], f["p2"], f["p3"]])
    cond = sev_p.max(0) / np.maximum(f["p_burn"], 1e-6)
    for tau in B_TAUS:
        out[f"hybrid_B_tau{tau}"] = np.where(burn, np.where(cond >= tau, pred, org), 0)
    logp = np.log(np.maximum(sev_p, 1e-8))
    onehot = np.stack([(org == c) for c in (1, 2, 3)]).astype(np.float32)
    for w in C_WEIGHTS:
        out[f"hybrid_C_w{w}"] = np.where(burn, 1 + (logp + w * onehot).argmax(0), 0)
    return out


def sample_rows(y, base, gt_boundary, rng, n_uniform=5000, n_hard=2000, n_c1=1500, n_bnd=1500):
    n = len(y)
    parts = [rng.choice(n, min(n, n_uniform), replace=False)]
    for mask, cap in ((y != base, n_hard), (y == 1, n_c1), (gt_boundary, n_bnd)):
        cand = np.nonzero(mask)[0]
        if len(cand):
            parts.append(rng.choice(cand, min(len(cand), cap), replace=False))
    return np.unique(np.concatenate(parts))


def gt_boundary01(gt: np.ndarray) -> np.ndarray:
    st = ndimage.generate_binary_structure(2, 2)
    near0 = ndimage.binary_dilation(gt == 0, st, iterations=2)
    near1 = ndimage.binary_dilation(gt == 1, st, iterations=2)
    return near0 & near1


def chip_path(cid: str) -> Path:
    return OUT_DIR / "chips" / f"{cid}.npz"


def load_chip_arrays(cid: str) -> dict:
    with np.load(chip_path(cid)) as d:
        c = {k: d[k] for k in d.files}
    c["valids"] = {"strict_mask": c.pop("valid_strict"), "all_valid_mask": c.pop("valid_all")}
    return c


def build(max_chips: int | None, th: dict, rng) -> tuple[dict, Tally, dict, dict]:
    folds = fold_of(load_meta())
    tally = Tally()
    oracle = {"agree": 0, "n": 0, "agree_global": 0}
    samples: dict = {}
    index: dict = {}
    (OUT_DIR / "chips").mkdir(parents=True, exist_ok=True)
    for k in range(1, N_FOLDS + 1):
        nd = np.load(OOF_DIR / f"cv_ndvi_f{k}.npz")
        du = np.load(OOF_DIR / f"cv_dual_f{k}.npz")
        ids = [str(x) for x in nd["ids"]]
        if ids != [str(x) for x in du["ids"]]:
            raise ValueError("v003 member OOF files disagree on chip order")
        ln, ld = nd["logits"], du["logits"]
        for i, cid in enumerate(ids[:max_chips]):
            if folds[cid] != k:
                raise ValueError(f"{cid} is not in fold {k}")
            logits = v003_logits(ln[i], ld[i])
            raw = load_raw(cid)
            f = pixel_features(raw, logits, th)
            gt = raw.mask.astype(np.int64)
            valids = {
                n: valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m) for n, m in EVAL_MODES.items()
            }
            crop = valids["all_valid_mask"] & (f["lc_group"] == CROP)
            chip = {
                "gt": gt,
                "valids": valids,
                "crop": crop,
                "crop_weak": crop & (f["dnbr"] > 0) & (f["dnbr"] < 0.177),
            }
            tally.record("v003", k, f["pred"], chip)
            tally.record("organizer_physics_full_scene", k, f["org_sev"], chip)
            for name, pred in hybrids(f, logits).items():
                tally.record(name, k, pred, chip)
            oracle_pred = np.where(gt > 0, np.clip(f["org_sev"], 1, 3), 0)
            tally.record("oracle_gt_contour_organizer_sev", k, oracle_pred, chip)
            inside = (gt > 0) & valids["all_valid_mask"]
            oracle["n"] += int(inside.sum())
            oracle["agree"] += int((oracle_pred[inside] == gt[inside]).sum())
            glob = 1 + np.digitize(f["dnbr"], (0.205, 0.39))
            oracle["agree_global"] += int((glob[inside] == gt[inside]).sum())
            gate = refine_gate(f, WIDE["band"], WIDE["radius"], WIDE["keep_conf"])
            gate &= valids["all_valid_mask"]
            sel = np.nonzero(gate.ravel())[0].astype(np.int32)
            X = stack(f, gate)
            y = gt.ravel()[sel].astype(np.uint8)
            base = f["pred"].astype(np.uint8)
            bnd = gt_boundary01(gt).ravel()[sel]
            np.savez(
                chip_path(cid),
                sel=sel,
                X=X,
                y=y,
                p_burn=f["p_burn"].ravel()[sel].astype(np.float32),
                dist=f["dist_pred_boundary"].ravel()[sel],
                base=base,
                gt=gt.astype(np.uint8),
                valid_strict=valids["strict_mask"],
                valid_all=valids["all_valid_mask"],
                crop=crop,
                crop_weak=chip["crop_weak"],
            )
            if len(y):
                rows = sample_rows(y, base.ravel()[sel], bnd, rng)
                samples[cid] = (X[rows], y[rows])
            index[cid] = {"fold": k, "gated": len(sel)}
        del nd, du, ln, ld
        print(f"fold {k} built, chips={len(index)}", flush=True)
    return index, tally, oracle, samples


def train_refiner(samples: dict, index: dict, k: int):
    import lightgbm as lgb

    parts = [v for cid, v in samples.items() if index[cid]["fold"] != k]
    X = np.concatenate([p[0] for p in parts])
    y = np.concatenate([p[1] for p in parts]).astype(np.int64)
    ds = lgb.Dataset(X, y, feature_name=list(FEATURES), categorical_feature=list(CATEGORICAL))
    params = {
        "objective": "multiclass",
        "num_class": NUM_CLASSES,
        "learning_rate": 0.05,
        "num_leaves": 63,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "num_threads": 4,
        "seed": SEED,
        "verbose": -1,
    }
    share = np.bincount(y, minlength=4) / len(y)
    print(f"fold {k} refiner rows={len(y)} class_share={share.round(3)}", flush=True)
    return lgb.train(params, ds, num_boost_round=400)


def gate_of(c: dict, band: float, radius: float) -> np.ndarray:
    gate = (c["p_burn"] >= band) & (c["p_burn"] <= 1 - band)
    if radius >= 0:
        gate |= np.abs(c["dist"]) <= radius
    return gate


def compose(c: dict, logp: np.ndarray, bias: np.ndarray, band: float, radius: float) -> np.ndarray:
    pred = c["base"].ravel().copy()
    gate = gate_of(c, band, radius)
    pred[c["sel"][gate]] = (logp[gate] + bias).argmax(1)
    return pred.reshape(c["gt"].shape)


def probs_path(cid: str) -> Path:
    return OUT_DIR / "chips" / f"{cid}_logp.npy"


def tune_bias(index: dict, band: float, radius: float) -> np.ndarray:
    fixed = zero_cm()
    ys, logps = [], []
    for cid in index:
        c = load_chip_arrays(cid)
        fixed += confusion(c["base"], c["gt"], c["valids"]["all_valid_mask"])
        g = gate_of(c, band, radius)
        fixed -= confusion(c["base"].ravel()[c["sel"][g]], c["y"][g], np.ones(g.sum(), bool))
        ys.append(c["y"][g])
        logps.append(np.load(probs_path(cid))[g])
    y = np.concatenate(ys)
    logp = np.concatenate(logps).astype(np.float32)
    ones = np.ones(len(y), bool)

    def score(b):
        return metrics_from_confusion(fixed + confusion((logp + b).argmax(1), y, ones))["bs_score"]

    grid = np.arange(-1.0, 1.01, 0.1)
    bias = np.zeros(NUM_CLASSES, dtype=np.float32)
    best = score(bias)
    for _ in range(2):
        for cls in (1, 2, 3):
            for value in grid:
                cand = bias.copy()
                cand[cls] = value
                sc = score(cand)
                if sc > best:
                    best, bias = sc, cand
    return bias


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--max-chips", type=int, default=None)
    args = p.parse_args()
    started = time.perf_counter()
    th = load_thresholds(THRESHOLDS)
    rng = np.random.default_rng(SEED)
    index, tally, oracle, samples = build(args.max_chips, th, rng)
    build_s = time.perf_counter() - started
    importance = {}
    t0 = time.perf_counter()
    for k in range(1, N_FOLDS + 1):
        booster = train_refiner(samples, index, k)
        importance[k] = dict(
            zip(FEATURES, booster.feature_importance("gain").round(1).tolist(), strict=True)
        )
        booster.save_model(str(OUT_DIR / f"refiner_oof_f{k}.txt"))
        for cid, meta in index.items():
            if meta["fold"] == k:
                X = np.load(chip_path(cid))["X"]
                probs = booster.predict(X) if len(X) else np.zeros((0, NUM_CLASSES))
                np.save(probs_path(cid), np.log(np.maximum(probs, 1e-9)).astype(np.float16))
    del samples
    refiner_s = time.perf_counter() - t0
    biases = {}
    for gname, (band, radius) in GATES.items():
        biases[gname] = tune_bias(index, band, radius)
    for cid, meta in index.items():
        c = load_chip_arrays(cid)
        logp = np.load(probs_path(cid)).astype(np.float32)
        for gname, (band, radius) in GATES.items():
            tally.record(
                f"refiner_{gname}_raw", meta["fold"], compose(c, logp, np.zeros(4), band, radius), c
            )
            tally.record(
                f"refiner_{gname}_oofbias",
                meta["fold"],
                compose(c, logp, biases[gname], band, radius),
                c,
            )
    gated = sum(m["gated"] for m in index.values())
    result = {
        "thresholds": json.loads(THRESHOLDS.read_text()),
        "chips": len(index),
        "gate_wide": WIDE,
        "gates": GATES,
        "gated_pixel_share": gated / (len(index) * 512 * 512),
        "oracle_inside_gt_contour_agreement": {
            "organizer_landcover": oracle["agree"] / max(oracle["n"], 1),
            "global_fit_dnbr": oracle["agree_global"] / max(oracle["n"], 1),
        },
        "refiner_bias": {k: v.tolist() for k, v in biases.items()},
        "feature_importance_gain": importance,
        "runtime_s": {"features": round(build_s, 1), "refiner_train_predict": round(refiner_s, 1)},
        "variants": summarize(tally),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, default=float) + "\n")
    skip = ("variants", "thresholds", "feature_importance_gain")
    print(json.dumps({k: v for k, v in result.items() if k not in skip}, indent=1, default=float))
    for name, e in result["variants"].items():
        a, s = e["all_valid_mask"], e["strict_mask"]
        pa = a["pooled"]
        print(
            f"{name:34s} all={a['bs_mean']:.4f} (worst {a['bs_worst']:.4f}) "
            f"strict={s['bs_mean']:.4f} "
            f"burn={pa['iou_burn']:.3f} iou={[round(x, 3) for x in pa['iou_per_class']]} "
            f"fp01={a['fp_0to1']:.4f} fn10={a['fn_1to0']:.3f} "
            f"cropfp01={e['crop_all_valid_fp_0to1']:.4f} "
            f"cropweakfp={e['crop_weak_dnbr_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
