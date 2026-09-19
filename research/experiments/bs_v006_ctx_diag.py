import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_contour_diag import CROP, GRASS, Tally
from bs_v006_prep import CTX_DIR, V005_OOF
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import group_map, load_thresholds
from kroma_ml.bs_v005 import EIGHT
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_v006_ctx_diag.json"
MODELS = ("ctx512", "ctx384")
TAUS = (0.5, 0.6, 0.7, 0.8, 0.9)


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    if not len(pos) or not len(neg):
        return float("nan")
    allv = np.concatenate([pos, neg])
    ranks = allv.argsort().argsort().astype(float)
    return float((ranks[: len(pos)].mean() - (len(pos) - 1) / 2) / len(neg))


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    _, val_ids = train_val_split(load_meta())
    tally = Tally()
    overlap = {m: {} for m in MODELS}
    comp_stats = {m: {"real": [], "false": [], "false_crop": [], "false_grass": []} for m in MODELS}
    for cid in val_ids:
        raw = load_raw(cid)
        gt = raw.mask.astype(np.int64)
        with np.load(V005_OOF / f"{cid}.npz") as z:
            v5, v5burn = z["label"].astype(np.int64), z["burn"]
        dnbr = spectral_indices(raw.refl)["dnbr"]
        lc = group_map(raw.landcover, th)
        valids = {n: valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m) for n, m in EVAL_MODES.items()}
        va = valids["all_valid_mask"]
        masks = {**valids, "crop": va & (lc == CROP), "grass": va & (lc == GRASS)}
        tally.add("v005", 1, v5, gt, masks)
        lab, n = ndimage.label(v5burn & va, EIGHT)
        idx = np.arange(1, n + 1)
        comp_overlap = ndimage.mean((gt > 0).astype(float), lab, idx) if n else np.zeros(0)
        comp_crop = ndimage.mean((lc == CROP).astype(float), lab, idx) if n else np.zeros(0)
        comp_grass = ndimage.mean((lc == GRASS).astype(float), lab, idx) if n else np.zeros(0)
        comp_area = ndimage.sum(np.ones_like(dnbr), lab, idx) if n else np.zeros(0)
        g_burn = gt > 0
        for m in MODELS:
            p = np.load(CTX_DIR / m / f"{cid}.npy").astype(np.float32)
            cpred = p.argmax(0)
            cburn = cpred > 0
            tally.add(m, 1, cpred, gt, masks)
            tally.add(f"oracle_pixel_v005_or_{m}", 1, np.where(cpred == gt, cpred, v5), gt, masks)
            reject = ndimage.mean((~cburn).astype(float), lab, idx) if n else np.zeros(0)
            pmean = ndimage.mean(1 - p[0], lab, idx) if n else np.zeros(0)
            is_real = comp_overlap >= 0.5
            for i in range(n):
                rec = (float(reject[i]), float(pmean[i]), float(comp_area[i]))
                if is_real[i]:
                    comp_stats[m]["real"].append(rec)
                else:
                    comp_stats[m]["false"].append(rec)
                    if comp_crop[i] >= 0.5:
                        comp_stats[m]["false_crop"].append(rec)
                    if comp_grass[i] >= 0.5:
                        comp_stats[m]["false_grass"].append(rec)
            best = np.where(is_real, 1.0, 0.0)
            oracle_keep = np.concatenate([[True], best > 0.5])[lab]
            tally.add(f"oracle_component_v005_drop_false_{m}_agrees", 1,
                      np.where((lab > 0) & ~oracle_keep & np.concatenate([[False], reject >= 0.5])[lab], 0, v5), gt, masks)  # fmt: skip
            for tau in TAUS:
                drop = np.concatenate([[False], reject >= tau])[lab]
                tally.add(f"drop_v005_comp_if_{m}_reject>={tau}", 1, np.where(drop, 0, v5), gt, masks)
            o = overlap[m]
            for key, sel in (("all", va), ("crop", masks["crop"]), ("grass", masks["grass"])):
                fp5, fpc = v5burn & ~g_burn & sel, cburn & ~g_burn & sel
                fn5, fnc = ~v5burn & g_burn & sel, ~cburn & g_burn & sel
                for name, val in (
                    ("fp_common", fp5 & fpc), ("fp_only_v005", fp5 & ~fpc), ("fp_only_ctx", fpc & ~fp5),
                    ("fn_common", fn5 & fnc), ("fn_only_v005", fn5 & ~fnc), ("fn_only_ctx", fnc & ~fn5),
                ):  # fmt: skip
                    o[f"{key}_{name}"] = o.get(f"{key}_{name}", 0) + int(val.sum())
            c1 = (gt == 1) & va
            o["class1_fn_only_v005"] = o.get("class1_fn_only_v005", 0) + int((c1 & ~v5burn & cburn).sum())
            o["class1_fn_only_ctx"] = o.get("class1_fn_only_ctx", 0) + int((c1 & v5burn & ~cburn).sum())
    summary = tally.summary()
    comp_out = {}
    for m, d in comp_stats.items():
        real = np.array(d["real"]) if d["real"] else np.zeros((0, 3))
        comp_out[m] = {}
        for key in ("false", "false_crop", "false_grass"):
            fal = np.array(d[key]) if d[key] else np.zeros((0, 3))
            comp_out[m][key] = {
                "n_real": len(real), "n_false": len(fal),
                "median_reject_real": float(np.median(real[:, 0])) if len(real) else None,
                "median_reject_false": float(np.median(fal[:, 0])) if len(fal) else None,
                "auc_reject_false_vs_real": auc(fal[:, 0], real[:, 0]),
                "area_weighted_reject_real": float((real[:, 0] * real[:, 2]).sum() / max(real[:, 2].sum(), 1)),
                "area_weighted_reject_false": float((fal[:, 0] * fal[:, 2]).sum() / max(fal[:, 2].sum(), 1)),
            }  # fmt: skip
    OUT_JSON.write_text(json.dumps({"chips": len(val_ids), "overlap": overlap, "components": comp_out, "variants": summary}, indent=2, default=float) + "\n")
    for m in MODELS:
        print(m, json.dumps(overlap[m]))
        print(m, json.dumps(comp_out[m]))
    base = summary["v005"]["all_valid_mask"]["bs_mean"]
    for name, e in sorted(summary.items(), key=lambda x: -x[1]["all_valid_mask"]["bs_mean"]):
        a = e["all_valid_mask"]
        print(
            f"{name:44s} all={a['bs_mean']:.4f} ({a['bs_mean'] - base:+.4f}) strict={e['strict_mask']['bs_mean']:.4f} "
            f"burn={a['iou_burn']:.3f} iou={[round(x, 3) for x in a['iou']]} fp0b={a['fp_0toburn']:.4f} "
            f"fn10={a['fn_1to0']:.3f} crop={e['crop_fp_0toburn']:.4f} grass={e['grass_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
