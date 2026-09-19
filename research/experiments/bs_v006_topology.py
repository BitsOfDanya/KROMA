import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_contour_diag import CROP, GRASS, Tally
from bs_v006_prep import V005_OOF
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map
from kroma_ml.bs_v005 import EIGHT
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_v006_topology.json"
DIST_BINS = (0, 1, 2, 3, 5, 10, np.inf)


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    tally = Tally()
    fn_hist = np.zeros(len(DIST_BINS) - 1, np.int64)
    fn_hole = fn_c1 = fn_total = 0
    fp_hist = np.zeros(len(DIST_BINS) - 1, np.int64)
    for cid in load_meta().chip_id:
        with np.load(V005_OOF / f"{cid}.npz") as z:
            v5, burn, k = z["label"].astype(np.int64), z["burn"], int(z["fold"])
        raw = load_raw(cid)
        gt = raw.mask.astype(np.int64)
        dnbr = spectral_indices(raw.refl)["dnbr"]
        org = np.clip(organizer_severity(dnbr, threshold_map(raw.landcover, th)), 1, 3)
        lc = group_map(raw.landcover, th)
        valids = {
            n: valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m) for n, m in EVAL_MODES.items()
        }
        va = valids["all_valid_mask"]
        masks = {**valids, "crop": va & (lc == CROP), "grass": va & (lc == GRASS)}
        tally.add("v005", k, v5, gt, masks)
        out_d = ndimage.distance_transform_edt(~burn) if burn.any() else np.full(gt.shape, 999.0)
        in_d = ndimage.distance_transform_edt(burn) if burn.any() else np.zeros(gt.shape)
        holes = ndimage.binary_fill_holes(burn) & ~burn
        fn = va & (gt > 0) & ~burn
        fp = va & (gt == 0) & burn
        fn_total += int(fn.sum())
        fn_hole += int((fn & holes).sum())
        fn_c1 += int((fn & (gt == 1)).sum())
        fn_hist += np.histogram(out_d[fn], bins=DIST_BINS)[0]
        fp_hist += np.histogram(in_d[fp], bins=DIST_BINS)[0]
        g_burn = gt > 0
        for r in (1, 2, 3):
            band = (out_d <= r) & (out_d > 0) | (in_d <= r) & (in_d > 0)
            fixed_burn = np.where(band, g_burn, burn)
            lbl = np.where(fixed_burn & burn, v5, np.where(fixed_burn, org, 0))
            tally.add(f"oracle_A_boundary_band{r}", k, lbl, gt, masks)
        for r in (2, 5, 10):
            zone = holes | ((out_d <= r) & (out_d > 0))
            add = zone & g_burn & ~burn
            tally.add(f"oracle_B_recover_near{r}_and_holes", k, np.where(add, org, v5), gt, masks)
        near = (out_d <= 5) & (out_d > 0)
        add_c1 = near & (gt == 1) & ~burn
        tally.add("oracle_B_class1_only_near5", k, np.where(add_c1, 1, v5), gt, masks)
        lab, n = ndimage.label(burn, EIGHT)
        if n:
            ov = ndimage.mean(g_burn.astype(float), lab, np.arange(1, n + 1))
            drop = np.concatenate([[False], ov < 0.5])[lab]
            tally.add("oracle_component_drop_remaining_false", k, np.where(drop, 0, v5), gt, masks)
    summary = tally.summary()
    res = {
        "fn_total": fn_total,
        "fn_in_holes_share": fn_hole / max(fn_total, 1),
        "fn_class1_share": fn_c1 / max(fn_total, 1),
        "fn_distance_to_v005_burn_px": dict(
            zip(
                ["<=1", "1-2", "2-3", "3-5", "5-10", ">10"],
                (fn_hist / fn_hist.sum()).round(4).tolist(),
                strict=True,
            )
        ),
        "fp_depth_inside_v005_burn_px": dict(
            zip(
                ["<=1", "1-2", "2-3", "3-5", "5-10", ">10"],
                (fp_hist / fp_hist.sum()).round(4).tolist(),
                strict=True,
            )
        ),
        "variants": summary,
    }
    OUT_JSON.write_text(json.dumps(res, indent=2, default=float) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "variants"}, indent=1))
    base = summary["v005"]["all_valid_mask"]["bs_mean"]
    for name, e in sorted(summary.items(), key=lambda x: -x[1]["all_valid_mask"]["bs_mean"]):
        a = e["all_valid_mask"]
        print(
            f"{name:40s} all={a['bs_mean']:.4f} ({a['bs_mean'] - base:+.4f}) burn={a['iou_burn']:.3f} iou={[round(x, 3) for x in a['iou']]}"
        )


if __name__ == "__main__":
    main()
