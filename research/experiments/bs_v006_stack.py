import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_components import COMP_DIR, COMP_FEATURES, POS_OVERLAP
from bs_v005_contour_diag import CROP, GRASS, V004_DIR, Tally
from bs_v005_refiner2 import CATEGORICAL, FEATURES, R2_DIR
from bs_v006_prep import V006
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, N_FOLDS, valid_mask
from kroma_ml.bs_data import load_chip, load_meta
from kroma_ml.bs_physics import _nd, spectral_indices
from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map
from kroma_ml.bs_v005 import compose_labels
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
EXTRA = V006 / "extra"
CTX_OOF = Path("/tmp/bs_oof")
CTX_ID = "ctx512cv"
SEED = 42
RE_PIX = (
    "dB5",
    "dB6",
    "dB7",
    "dNDRE5",
    "dNDRE6",
    "dNDRE7",
    "NDRE7_post",
    "dB5_mean11",
    "dNDRE7_mean11",
)
RE_COMP = ("re_dB5", "re_dB6", "re_dB7", "re_dNDRE5", "re_dNDRE6", "re_dNDRE7", "re_NDRE7_post",
           "re_dB5_contrast", "re_dNDRE7_contrast")  # fmt: skip
CTX_PIX = ("ctx_pburn", "ctx_p1", "ctx_diff", "ctx_agree", "ctx_pburn_mean11", "ctx_comp_reject")
CTX_COMP = (
    "ctx_mean",
    "ctx_max",
    "ctx_p1_mean",
    "ctx_p1_max",
    "ctx_reject",
    "ctx_diff_mean",
    "ctx_ring_mean",
)
RULES = [(ct, at, rt) for ct in (0.3, 0.4) for at in (0.7, 0.8) for rt in (0.2, 0.3)]
COMP_PARAMS = {
    "objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 20,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "num_threads": 4, "seed": SEED, "verbose": -1, "deterministic": True,
}  # fmt: skip
PIX_PARAMS = {**COMP_PARAMS, "num_leaves": 63, "min_data_in_leaf": 200}


def rededge_maps(cid: str) -> dict:
    chip = load_chip(cid, with_mask=False)

    def s(w, b):
        return chip.s2(w, b) / 10000.0

    out = {f"d{b}": s("post", b) - s("pre", b) for b in ("B5", "B6", "B7")}
    for i, b in ((5, "B5"), (6, "B6"), (7, "B7")):
        pre, post = _nd(s("pre", "B8A"), s("pre", b)), _nd(s("post", "B8A"), s("post", b))
        out[f"dNDRE{i}"] = pre - post
        if i == 7:
            out["NDRE7_post"] = post
    out["dB5_mean11"] = ndimage.uniform_filter(out["dB5"], 11)
    out["dNDRE7_mean11"] = ndimage.uniform_filter(out["dNDRE7"], 11)
    return out


def comp_stats(lab: np.ndarray, maps: list[np.ndarray]) -> np.ndarray:
    n = int(lab.max())
    if not n:
        return np.zeros((0, len(maps)), np.float32)
    idx = np.arange(1, n + 1)
    return np.stack([ndimage.mean(m, lab, idx) for m in maps], 1).astype(np.float32)


def ring_contrast(lab: np.ndarray, x: np.ndarray) -> np.ndarray:
    n = int(lab.max())
    if not n:
        return np.zeros(0, np.float32)
    idx = np.arange(1, n + 1)
    ring = ndimage.grey_dilation(lab, footprint=np.ones((11, 11)))
    ring = np.where(lab == 0, ring, 0)
    inner = ndimage.mean(x, lab, idx)
    outer = ndimage.sum(x, ring, idx) / np.maximum(ndimage.sum(np.ones_like(x), ring, idx), 1)
    return (inner - outer).astype(np.float32)


def load_ctx() -> dict[str, np.ndarray]:
    out = {}
    for k in range(1, N_FOLDS + 1):
        d = np.load(CTX_OOF / f"{CTX_ID}_f{k}.npz")
        for cid, lg in zip(d["ids"], d["logits"], strict=True):
            out[str(cid)] = lg
    return out


def ctx_probs(logits: np.ndarray) -> np.ndarray:
    z = logits.astype(np.float32)
    z = np.exp(z - z.max(0, keepdims=True))
    return z / z.sum(0, keepdims=True)


def build_extra(group: str) -> None:
    EXTRA.mkdir(parents=True, exist_ok=True)
    ctx = load_ctx() if group == "ctx" else None
    for cid in load_meta().chip_id:
        lab = np.load(COMP_DIR / f"{cid}.npz")["lab"]
        sel = np.load(R2_DIR / f"{cid}_sel.npy")
        if group == "re":
            m = rededge_maps(cid)
            comp = np.concatenate(
                [comp_stats(lab, [m[k] for k in RE_PIX[:7]]),
                 np.stack([ring_contrast(lab, m["dB5"]), ring_contrast(lab, m["dNDRE7"])], 1).reshape(-1, 2)],
                1,
            )  # fmt: skip
            pix = np.stack([m[k].ravel()[sel] for k in RE_PIX], 1)
        else:
            p = ctx_probs(ctx[cid])
            with np.load(V004_DIR / f"{cid}.npz") as z:
                pv = 1 - z["probs"][0].astype(np.float32)
            pc = 1 - p[0]
            reject = (p.argmax(0) == 0).astype(np.float32)
            n = int(lab.max())
            idx = np.arange(1, n + 1)
            if n:
                comp = np.stack(
                    [ndimage.mean(pc, lab, idx), ndimage.maximum(pc, lab, idx), ndimage.mean(p[1], lab, idx),
                     ndimage.maximum(p[1], lab, idx), ndimage.mean(reject, lab, idx),
                     ndimage.mean(pv - pc, lab, idx), ring_contrast(lab, pc)],
                    1,
                ).astype(np.float32)  # fmt: skip
                comp_reject_px = np.concatenate([[-1.0], comp[:, 4]])[lab]
            else:
                comp = np.zeros((0, len(CTX_COMP)), np.float32)
                comp_reject_px = np.full(lab.shape, -1.0, np.float32)
            maps = [pc, p[1], pv - pc, ((pc >= 0.5) == (pv >= 0.5)).astype(np.float32),
                    ndimage.uniform_filter(pc, 11), comp_reject_px]  # fmt: skip
            pix = np.stack([m.ravel()[sel] for m in maps], 1)
        np.save(EXTRA / f"{cid}_{group}_comp.npy", comp.astype(np.float32))
        np.save(EXTRA / f"{cid}_{group}_pix.npy", pix.astype(np.float16))
    print(f"extra features {group} built", flush=True)


def groups_for(config: str) -> list[str]:
    return {"A": [], "C": ["re"], "B": ["ctx"], "D": ["ctx", "re"]}[config]


def load_comp(cid: str, groups: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(COMP_DIR / f"{cid}.npz") as z:
        feats, overlap, lab = z["feats"], z["overlap"], z["lab"]
    parts = [feats] + [np.load(EXTRA / f"{cid}_{g}_comp.npy") for g in groups]
    area = np.bincount(lab.ravel(), minlength=len(feats) + 1)[1:] if len(feats) else np.zeros(0)
    return (
        np.concatenate(parts, 1) if len(feats) else np.zeros((0, sum(p.shape[1] for p in parts))),
        overlap,
        area,
    )


def pixel_rows(cid: str, groups: list[str], rng) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = np.load(R2_DIR / f"{cid}_X.npy").astype(np.float32)
    sel = np.load(R2_DIR / f"{cid}_sel.npy")
    extra = [np.load(EXTRA / f"{cid}_{g}_pix.npy").astype(np.float32) for g in groups]
    X = np.concatenate([X, *extra], 1) if extra else X
    gt = load_raw(cid).mask.ravel()[sel]
    pred = np.load(V004_DIR / f"{cid}.npz")["pred"].ravel()[sel]
    y, base = (gt > 0).astype(np.uint8), (pred > 0).astype(np.uint8)
    bnd = np.abs(X[:, FEATURES.index("dist_boundary")]) <= 2
    if not len(y):
        return X[:0], y[:0], X
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
    return X[rows], y[rows], X


def names_for(groups: list[str]) -> tuple[list[str], list[str]]:
    comp = list(COMP_FEATURES) + [n for g in groups for n in (CTX_COMP if g == "ctx" else RE_COMP)]
    pix = list(FEATURES) + [n for g in groups for n in (CTX_PIX if g == "ctx" else RE_PIX)]
    return comp, pix


def run(config: str) -> dict:
    groups = groups_for(config)
    comp_names, pix_names = names_for(groups)
    th = load_thresholds(THRESHOLDS)
    meta = load_meta()
    fold = {cid: int(np.load(V004_DIR / f"{cid}.npz")["fold"]) for cid in meta.chip_id}
    comp_data = {cid: load_comp(cid, groups) for cid in meta.chip_id}
    rng = np.random.default_rng(SEED)
    pix_samples = {}
    for cid in meta.chip_id:
        Xs, ys, _ = pixel_rows(cid, groups, rng)
        pix_samples[cid] = (Xs, ys)
    comp_prob, pix_prob, imp_c, imp_p = {}, {}, np.zeros(len(comp_names)), np.zeros(len(pix_names))
    for k in range(1, N_FOLDS + 1):
        tr = [c for c in meta.chip_id if fold[c] != k]
        Xc = np.concatenate([comp_data[c][0] for c in tr])
        yc = np.concatenate([(comp_data[c][1] >= POS_OVERLAP).astype(np.int64) for c in tr])
        wc = np.log1p(np.concatenate([comp_data[c][2] for c in tr]))
        bc = lgb.train(COMP_PARAMS, lgb.Dataset(Xc, yc, weight=wc, feature_name=comp_names), 300)
        Xp = np.concatenate([pix_samples[c][0] for c in tr])
        yp = np.concatenate([pix_samples[c][1] for c in tr])
        cats = [n for n in CATEGORICAL if n in pix_names]
        bp = lgb.train(
            PIX_PARAMS, lgb.Dataset(Xp, yp, feature_name=pix_names, categorical_feature=cats), 500
        )
        imp_c += bc.feature_importance("gain")
        imp_p += bp.feature_importance("gain")
        for c in (c for c in meta.chip_id if fold[c] == k):
            comp_prob[c] = bc.predict(comp_data[c][0]) if len(comp_data[c][0]) else np.zeros(0)
            _, _, Xall = pixel_rows(c, groups, np.random.default_rng(0))
            pix_prob[c] = bp.predict(Xall) if len(Xall) else np.zeros(0)
            save = V006 / f"stack_{config}"
            save.mkdir(parents=True, exist_ok=True)
            np.save(save / f"{c}_comp.npy", comp_prob[c].astype(np.float32))
            np.save(save / f"{c}_pix.npy", pix_prob[c].astype(np.float32))
        print(f"[{config}] fold {k} trained", flush=True)
    tally = Tally()
    for cid in meta.chip_id:
        k = fold[cid]
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
        sel = np.load(R2_DIR / f"{cid}_sel.npy")
        r2 = np.zeros(gt.size, np.float32)
        r2[sel] = pix_prob[cid]
        zone = np.zeros(gt.size, bool)
        zone[sel] = True
        r2, zone = r2.reshape(gt.shape), zone.reshape(gt.shape)
        base = pred > 0
        for ct, at, rt in RULES:
            removed = (lab > 0) & (cp < ct)
            burn = (base & ~removed & ~(zone & (r2 < rt))) | (~removed & zone & (r2 >= at))
            lbl = np.where(burn & base, pred, compose_labels(burn, probs, org))
            tally.add(f"{config}_c{ct}_a{at}_r{rt}", k, lbl, gt, masks)
    summary = tally.summary()
    return {
        "config": config,
        "groups": groups,
        "comp_importance": dict(
            zip(comp_names, (imp_c / imp_c.sum()).round(4).tolist(), strict=True)
        ),
        "pix_importance": dict(
            zip(pix_names, (imp_p / imp_p.sum()).round(4).tolist(), strict=True)
        ),
        "variants": summary,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--build", choices=("re", "ctx"))
    p.add_argument("--config", choices=("A", "B", "C", "D"))
    args = p.parse_args()
    if args.build:
        build_extra(args.build)
    if args.config:
        res = run(args.config)
        out = REPO / "research" / "experiments" / f"bs_v006_stack_{args.config}.json"
        out.write_text(json.dumps(res, indent=2, default=float) + "\n")
        for name, e in sorted(
            res["variants"].items(), key=lambda x: -x[1]["all_valid_mask"]["bs_mean"]
        )[:4]:
            a = e["all_valid_mask"]
            print(
                f"{name:24s} all={a['bs_mean']:.4f} worst={a['bs_worst']:.4f} "
                f"folds={[round(v, 4) for v in a['per_fold'].values()]} strict={e['strict_mask']['bs_mean']:.4f} "
                f"burn={a['iou_burn']:.3f} iou={[round(x, 3) for x in a['iou']]} fp01={a['fp_0to1']:.4f} "
                f"fp0b={a['fp_0toburn']:.4f} fn10={a['fn_1to0']:.3f} crop={e['crop_fp_0toburn']:.4f} "
                f"grass={e['grass_fp_0toburn']:.4f}"
            )
        top = sorted(res["comp_importance"].items(), key=lambda x: -x[1])[:8]
        print("comp top", top)


if __name__ == "__main__":
    main()
