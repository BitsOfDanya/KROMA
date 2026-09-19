import json
from pathlib import Path

import numpy as np
from bs_v004_fasttrack import (
    OOF_DIR,
    THRESHOLDS,
    Tally,
    gate_of,
    hybrids,
    load_chip_arrays,
    probs_path,
    summarize,
)
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import N_FOLDS
from kroma_ml.bs_v004 import load_thresholds, pixel_features, softmax, v003_logits

REPO = Path(__file__).resolve().parents[2]
V004_DIR = REPO / "data" / "processed" / "bs_v005" / "oof_v004"
COMBO = REPO / "research" / "experiments" / "bs_v004_combo_results.json"
BAND, RADIUS = 0.3, 2.0


def v004_maps(c: dict, logits: np.ndarray, f: dict, logp: np.ndarray, bias: np.ndarray) -> dict:
    probs = softmax(logits)
    flat = probs.reshape(4, -1).copy()
    gate = gate_of(c, BAND, RADIUS)
    refined = np.exp(logp[gate] + bias)
    refined /= refined.sum(1, keepdims=True)
    flat[:, c["sel"][gate]] = refined.T
    probs = flat.reshape(probs.shape)
    pred = probs.argmax(0)
    final = hybrids({**f, "pred": pred}, logits)["hybrid_C_w1.0"]
    return {"probs": probs, "pred": final}


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    bias = np.asarray(json.loads(COMBO.read_text())["biases"]["band30_r2"], np.float32)
    V004_DIR.mkdir(parents=True, exist_ok=True)
    tally = Tally()
    for k in range(1, N_FOLDS + 1):
        nd, du = np.load(OOF_DIR / f"cv_ndvi_f{k}.npz"), np.load(OOF_DIR / f"cv_dual_f{k}.npz")
        ln, ld = nd["logits"], du["logits"]
        for i, cid in enumerate(str(x) for x in nd["ids"]):
            logits = v003_logits(ln[i], ld[i])
            f = pixel_features(load_raw(cid), logits, th)
            c = load_chip_arrays(cid)
            logp = np.load(probs_path(cid)).astype(np.float32)
            m = v004_maps(c, logits, f, logp, bias)
            tally.record("v004", k, m["pred"], c)
            np.savez(
                V004_DIR / f"{cid}.npz",
                pred=m["pred"].astype(np.uint8),
                probs=m["probs"].astype(np.float16),
                fold=np.int8(k),
            )
        del nd, du, ln, ld
        print(f"fold {k} done", flush=True)
    e = summarize(tally)["v004"]
    print(json.dumps({m: e[m]["bs_mean"] for m in ("all_valid_mask", "strict_mask")}))


if __name__ == "__main__":
    main()
