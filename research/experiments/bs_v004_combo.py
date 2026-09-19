import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import (
    OOF_DIR,
    THRESHOLDS,
    Tally,
    compose,
    hybrids,
    load_chip_arrays,
    probs_path,
    summarize,
    tune_bias,
)
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import N_FOLDS
from kroma_ml.bs_v004 import load_thresholds, pixel_features, v003_logits

REPO = Path(__file__).resolve().parents[2]
FAST = REPO / "research" / "experiments" / "bs_v004_fasttrack_results.json"
OUT_JSON = REPO / "research" / "experiments" / "bs_v004_combo_results.json"
GATES = {"band20_r2": (0.20, 2.0), "band30_r2": (0.30, 2.0), "band25_r1": (0.25, 1.0)}
HYBRIDS = ("hybrid_C_w1.0", "hybrid_B_tau0.7")


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    fast = json.loads(FAST.read_text())
    index = {}
    for k in range(1, N_FOLDS + 1):
        with np.load(OOF_DIR / f"cv_ndvi_f{k}.npz") as d:
            index.update({str(c): k for c in d["ids"]})
    biases = {"band20_r2": np.asarray(fast["refiner_bias"]["band20_r2"], np.float32)}
    for g, (band, radius) in GATES.items():
        if g not in biases:
            biases[g] = tune_bias({c: {"fold": k} for c, k in index.items()}, band, radius)
    tally = Tally()
    for k in range(1, N_FOLDS + 1):
        nd, du = np.load(OOF_DIR / f"cv_ndvi_f{k}.npz"), np.load(OOF_DIR / f"cv_dual_f{k}.npz")
        ln, ld = nd["logits"], du["logits"]
        for i, cid in enumerate(str(x) for x in nd["ids"]):
            logits = v003_logits(ln[i], ld[i])
            f = pixel_features(load_raw(cid), logits, th)
            c = load_chip_arrays(cid)
            logp = np.load(probs_path(cid)).astype(np.float32)
            tally.record("v003", k, f["pred"], c)
            for g, (band, radius) in GATES.items():
                refined = compose(c, logp, biases[g], band, radius).astype(np.int64)
                tally.record(f"refiner_{g}", k, refined, c)
                fr = {**f, "pred": refined}
                out = hybrids(fr, logits)
                for h in HYBRIDS:
                    tally.record(f"refiner_{g}+{h}", k, out[h], c)
        print(f"fold {k} done", flush=True)
    result = {"biases": {g: b.tolist() for g, b in biases.items()}, "variants": summarize(tally)}
    OUT_JSON.write_text(json.dumps(result, indent=2, default=float) + "\n")
    for name, e in result["variants"].items():
        a, s = e["all_valid_mask"], e["strict_mask"]
        pa = a["pooled"]
        folds = [round(v, 4) for v in a["per_fold"].values()]
        print(
            f"{name:38s} all={a['bs_mean']:.4f} folds={folds} strict={s['bs_mean']:.4f} "
            f"burn={pa['iou_burn']:.3f} iou={[round(x, 3) for x in pa['iou_per_class']]} "
            f"fp01={a['fp_0to1']:.4f} fn10={a['fn_1to0']:.3f} "
            f"cropfp01={e['crop_all_valid_fp_0to1']:.4f}"
        )


if __name__ == "__main__":
    main()
