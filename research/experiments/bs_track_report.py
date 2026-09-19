import argparse
import json
import os
from pathlib import Path

import numpy as np
from kroma_ml.bs_cv import EVAL_MODES, N_FOLDS, summarize_folds

REPO = Path(__file__).resolve().parents[2]
TRACK = Path(os.environ.get("KROMA_BS_TRACK_DIR", REPO / "data" / "processed" / "bs_track"))
OUT_JSON = REPO / "research" / "experiments" / "bs_track_results.json"


def run_summary(run_id: str) -> dict | None:
    files = [TRACK / f"{run_id}_f{k}.json" for k in range(1, N_FOLDS + 1)]
    if not all(f.exists() for f in files):
        return None
    folds = [json.loads(f.read_text()) for f in files]
    out = {
        "id": run_id,
        "args": folds[0]["args"],
        "params": folds[0]["params"],
        "train_seconds_mean": float(np.mean([f["train_seconds"] for f in folds])),
        "sampler": folds[0]["sampler"],
    }
    for name in EVAL_MODES:
        per_fold = {k + 1: f[name] for k, f in enumerate(folds)}
        pooled = sum(np.asarray(f[name]["confusion"]) for f in folds)
        out[name] = summarize_folds(per_fold, pooled)
    return out


def row(summary: dict, mode: str = "all_valid_mask") -> dict:
    s, p = summary[mode]["summary"], summary[mode]["pooled"]
    return {
        "bs_mean": s["bs_score"]["mean"],
        "bs_std": s["bs_score"]["std"],
        "bs_worst": s["bs_score"]["min"],
        "bs_pooled": p["bs_score"],
        "iou1": p["iou_per_class"][1],
        "p1": p["precision_per_class"][1],
        "r1": p["recall_per_class"][1],
        "f1_1": p["f1_per_class"][1],
        "iou_burn": p["iou_burn"],
        "miou": p["miou_all"],
        "iou": p["iou_per_class"],
    }


def collect(ids: list[str]) -> dict:
    out = {}
    for run_id in ids:
        s = run_summary(run_id)
        if s is not None:
            out[run_id] = s
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("ids", nargs="*")
    args = p.parse_args()
    ids = args.ids or sorted({f.stem.rsplit("_f", 1)[0] for f in TRACK.glob("*_f[123].json")})
    runs = collect(ids)
    existing = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    existing.setdefault("runs", {}).update(runs)
    OUT_JSON.write_text(json.dumps(existing, indent=2, default=float) + "\n")
    for run_id, s in runs.items():
        for mode in EVAL_MODES:
            r = row(s, mode)
            print(
                f"{run_id:18s} {mode:15s} bs={r['bs_mean']:.4f}±{r['bs_std']:.4f} "
                f"worst={r['bs_worst']:.4f} pooled={r['bs_pooled']:.4f} iou1={r['iou1']:.3f} "
                f"P1={r['p1']:.3f} R1={r['r1']:.3f} "
                f"burn={r['iou_burn']:.3f} miou={r['miou']:.3f}"
            )


if __name__ == "__main__":
    main()
