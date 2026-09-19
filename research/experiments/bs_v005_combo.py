import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import THRESHOLDS
from bs_v005_components import COMP_DIR
from bs_v005_contour_diag import CROP, GRASS, V004_DIR, Tally
from bs_v005_refiner2 import R2_DIR
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import EVAL_MODES, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map
from kroma_ml.bs_v005 import compose_labels

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_v005_combo.json"
COMP_T = (0.3, 0.4)
ADD_T = (0.5, 0.6, 0.7, 0.8, 1.01)
RM_T = (0.0, 0.1, 0.2, 0.3)
BLEND_W = (0.3, 0.5, 0.7)
BLEND_T = (0.35, 0.4, 0.45, 0.5)


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    tally = Tally()
    for cid in load_meta().chip_id:
        with np.load(V004_DIR / f"{cid}.npz") as z:
            pred, probs, k = (
                z["pred"].astype(np.int64),
                z["probs"].astype(np.float32),
                int(z["fold"]),
            )
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
        cp = np.load(COMP_DIR / f"{cid}_prob.npy").astype(np.float32)
        r2 = np.zeros(gt.size, np.float32)
        r2[np.load(R2_DIR / f"{cid}_sel.npy")] = np.load(R2_DIR / f"{cid}_p.npy").astype(np.float32)
        r2 = r2.reshape(gt.shape)
        in_zone = np.zeros(gt.size, bool)
        in_zone[np.load(R2_DIR / f"{cid}_sel.npy")] = True
        in_zone = in_zone.reshape(gt.shape)
        tally.add("v004", k, pred, gt, masks)
        base_burn = pred > 0
        for ct in COMP_T:
            removed = (lab > 0) & (cp < ct)
            kept = base_burn & ~removed
            for at in ADD_T:
                for rt in RM_T:
                    burn = (kept & ~(in_zone & (r2 < rt))) | (~removed & in_zone & (r2 >= at))
                    lbl = np.where(burn & base_burn, pred, compose_labels(burn, probs, org))
                    tally.add(f"comp{ct}_add{at}_rm{rt}", k, lbl, gt, masks)
        comp_keep = np.where(lab > 0, cp, np.where(base_burn, 1.0, 0.0))
        for w in BLEND_W:
            score = np.where(
                in_zone, w * r2 + (1 - w) * np.minimum(comp_keep, 1.0) * (1 - probs[0]), 0.0
            )
            for bt in BLEND_T:
                burn = score >= bt
                lbl = np.where(burn & base_burn, pred, compose_labels(burn, probs, org))
                tally.add(f"blend_w{w}_t{bt}", k, lbl, gt, masks)
    summary = tally.summary()
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=float) + "\n")
    base = summary["v004"]["all_valid_mask"]["bs_mean"]
    ranked = sorted(summary.items(), key=lambda x: -x[1]["all_valid_mask"]["bs_mean"])
    for name, e in ranked[:15] + [("v004", summary["v004"])]:
        a = e["all_valid_mask"]
        print(
            f"{name:26s} all={a['bs_mean']:.4f} ({a['bs_mean'] - base:+.4f}) worst={a['bs_worst']:.4f} "
            f"folds={[round(v, 4) for v in a['per_fold'].values()]} strict={e['strict_mask']['bs_mean']:.4f} "
            f"burn={a['iou_burn']:.3f} iou={[round(x, 3) for x in a['iou']]} fp0b={a['fp_0toburn']:.4f} "
            f"fn10={a['fn_1to0']:.3f} crop={e['crop_fp_0toburn']:.4f} grass={e['grass_fp_0toburn']:.4f}"
        )


if __name__ == "__main__":
    main()
