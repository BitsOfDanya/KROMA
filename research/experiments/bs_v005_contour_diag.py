import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import OOF_DIR, THRESHOLDS
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, N_FOLDS, confusion, metrics_from_confusion, valid_mask
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import (
    GROUP_ORDER,
    group_map,
    load_thresholds,
    organizer_severity,
    threshold_map,
    v003_logits,
)
from kroma_ml.bs_v005 import (
    clean_core,
    compose_labels,
    distance_conditioned,
    distance_histogram,
    distance_to,
    hysteresis,
)

REPO = Path(__file__).resolve().parents[2]
V004_DIR = REPO / "data" / "processed" / "bs_v005" / "oof_v004"
OUT_JSON = REPO / "research" / "experiments" / "bs_v005_contour_diag.json"
CROP, GRASS = GROUP_ORDER.index("cropland"), GROUP_ORDER.index("grassland")


def configs() -> dict:
    out = {"thr_0.5": ("thr", 0.5)}
    for t in (0.4, 0.45, 0.55, 0.6, 0.65):
        out[f"thr_{t}"] = ("thr", t)
    for th in (0.7, 0.8, 0.9):
        for tl in (0.3, 0.4, 0.5):
            for r in (0, 2):
                out[f"hyst_h{th}_l{tl}_r{r}"] = ("hyst", th, tl, r)
    for near in (5, 15):
        for tn in (0.35, 0.45):
            for tf in (0.55, 0.65, 0.75):
                out[f"distcond_n{near}_tn{tn}_tf{tf}"] = ("dist", near, tn, tf)
    for tl in (0.2, 0.3, 0.4):
        out[f"hystphys_h0.8_l{tl}"] = ("hystphys", 0.8, tl)
    return out


class Tally:
    def __init__(self) -> None:
        self.cm: dict = {}

    def add(self, name: str, fold: int, pred: np.ndarray, gt: np.ndarray, masks: dict) -> None:
        d = self.cm.setdefault(name, {})
        for key, m in masks.items():
            d.setdefault(key, {}).setdefault(fold, np.zeros((4, 4), np.int64))
            d[key][fold] += confusion(pred, gt, m)

    def summary(self) -> dict:
        out = {}
        for name, d in self.cm.items():
            e = {}
            for key in ("all_valid_mask", "strict_mask"):
                per = {k: metrics_from_confusion(cm)["bs_score"] for k, cm in d[key].items()}
                pooled = metrics_from_confusion(sum(d[key].values()))
                e[key] = {
                    "bs_mean": float(np.mean(list(per.values()))),
                    "bs_worst": float(min(per.values())),
                    "per_fold": per,
                    "iou_burn": pooled["iou_burn"],
                    "iou": pooled["iou_per_class"],
                    "fp_0to1": pooled["row_normalized"][0][1],
                    "fp_0toburn": float(1 - pooled["row_normalized"][0][0]),
                    "fn_1to0": pooled["row_normalized"][1][0],
                }
            for key in ("crop", "grass"):
                cm = sum(d[key].values())
                e[f"{key}_fp_0toburn"] = float(cm[0, 1:].sum() / max(cm[0].sum(), 1))
            out[name] = e
        return out


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    cfgs = configs()
    tally = Tally()
    pops = ("gt_class1", "v004_fp_burn", "v004_fp_crop", "bg_burnlike", "v004_fn_burn")
    cores = ("core_gt23", "core_pred", "core_phys")
    hist = {c: {p: np.zeros(len((2, 5, 10, 20)) + 1, np.int64) for p in pops} for c in cores}
    for k in range(1, N_FOLDS + 1):
        nd, du = np.load(OOF_DIR / f"cv_ndvi_f{k}.npz"), np.load(OOF_DIR / f"cv_dual_f{k}.npz")
        ln, ld = nd["logits"], du["logits"]
        for i, cid in enumerate(str(x) for x in nd["ids"]):
            raw = load_raw(cid)
            gt = raw.mask.astype(np.int64)
            with np.load(V004_DIR / f"{cid}.npz") as z:
                pred4, probs = z["pred"].astype(np.int64), z["probs"].astype(np.float32)
            p_burn = 1.0 - probs[0]
            dnbr = spectral_indices(raw.refl)["dnbr"]
            org = organizer_severity(dnbr, threshold_map(raw.landcover, th))
            lc = group_map(raw.landcover, th)
            valids = {
                n: valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m) for n, m in EVAL_MODES.items()
            }
            va = valids["all_valid_mask"]
            masks = {**valids, "crop": va & (lc == CROP), "grass": va & (lc == GRASS)}
            v003 = v003_logits(ln[i], ld[i]).argmax(0)
            tally.add("v004", k, pred4, gt, masks)
            tally.add("v003", k, v003, gt, masks)
            core_pred = clean_core((p_burn >= 0.8) | (pred4 >= 2), 20)
            dist = {
                "core_gt23": distance_to(gt >= 2),
                "core_pred": distance_to(core_pred),
                "core_phys": distance_to(clean_core(org >= 2, 50)),
            }
            sel = {
                "gt_class1": va & (gt == 1),
                "v004_fp_burn": va & (gt == 0) & (pred4 > 0),
                "v004_fp_crop": va & (gt == 0) & (pred4 > 0) & (lc == CROP),
                "bg_burnlike": va & (gt == 0) & (org >= 1),
                "v004_fn_burn": va & (gt > 0) & (pred4 == 0),
            }
            for c in cores:
                for p in pops:
                    hist[c][p] += distance_histogram(dist[c], sel[p])
            sev_fill = compose_labels(np.ones_like(gt, bool), probs, org)
            tally.add(
                "oracle_A_gt_contour_v004_severity",
                k,
                np.where(gt > 0, np.where(pred4 > 0, pred4, sev_fill), 0),
                gt,
                masks,
            )
            tally.add(
                "oracle_B_v004_contour_gt_severity",
                k,
                np.where((pred4 > 0) & (gt > 0), gt, pred4),
                gt,
                masks,
            )
            tally.add(
                "oracle_C_gt_contour_organizer",
                k,
                np.where(gt > 0, np.clip(org, 1, 3), 0),
                gt,
                masks,
            )
            tally.add("oracle_D_best_of_v003_v004", k, np.where(v003 == gt, v003, pred4), gt, masks)
            for name, cfg in cfgs.items():
                if cfg[0] == "thr":
                    burn = p_burn >= cfg[1]
                elif cfg[0] == "hyst":
                    burn = hysteresis(p_burn, cfg[1], cfg[2], cfg[3])
                elif cfg[0] == "dist":
                    burn = distance_conditioned(p_burn, dist["core_pred"], cfg[1], cfg[2], cfg[3])
                else:
                    gated = np.where(
                        org >= 1, p_burn, np.minimum(p_burn, cfg[2] - 1e-3 + 0 * p_burn)
                    )
                    gated = np.where(p_burn >= 0.5, p_burn, gated)
                    burn = hysteresis(gated, cfg[1], cfg[2], 0)
                tally.add(name, k, compose_labels(burn, probs, org), gt, masks)
        del nd, du, ln, ld
        print(f"fold {k} done", flush=True)
    result = {
        "core_distance_hist_bins": ["<=2", "2-5", "5-10", "10-20", ">20"],
        "core_distance_hist": {
            c: {p: (h / max(h.sum(), 1)).round(4).tolist() + [int(h.sum())] for p, h in d.items()}
            for c, d in hist.items()
        },
        "variants": tally.summary(),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2, default=float) + "\n")
    for c, d in result["core_distance_hist"].items():
        for p, v in d.items():
            print(f"{c:10s} {p:14s} {v}")
    base = result["variants"]["v004"]["all_valid_mask"]["bs_mean"]
    for name, e in sorted(
        result["variants"].items(), key=lambda x: -x[1]["all_valid_mask"]["bs_mean"]
    ):
        a = e["all_valid_mask"]
        print(
            f"{name:34s} all={a['bs_mean']:.4f} ({a['bs_mean'] - base:+.4f}) worst={a['bs_worst']:.4f} "
            f"strict={e['strict_mask']['bs_mean']:.4f} burn={a['iou_burn']:.3f} "
            f"iou1={a['iou'][1]:.3f} fp0b={a['fp_0toburn']:.4f} fn10={a['fn_1to0']:.3f} "
            f"crop={e['crop_fp_0toburn']:.4f} grass={e['grass_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
