import argparse
import json
from pathlib import Path

import numpy as np
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import (
    EVAL_MODES,
    confusion,
    evaluate_scenes,
    fold_of,
    summarize_folds,
    valid_mask,
)
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_metrics import NUM_CLASSES
from kroma_ml.bs_physics import spectral_indices

REPO = Path(__file__).resolve().parents[2]
PHYSICS_JSON = REPO / "research" / "experiments" / "bs_physics_baseline_results.json"
OUT_JSON = REPO / "research" / "experiments" / "bs_fusion_results.json"
OOF_DIR = REPO / "data" / "processed" / "bs_oof"
VARIANTS = ("ml", "ml_burn_phys_sev", "ml_burn_phys_sev_keep1")


def fold_thresholds() -> dict[int, tuple[float, float, float]]:
    entry = json.loads(PHYSICS_JSON.read_text())["variants"]["fit_dnbr"]["all_valid_mask"]
    return {int(k): tuple(v["thresholds"]) for k, v in entry["params_per_fold"].items()}


def fuse(logits: np.ndarray, dnbr: np.ndarray, t: tuple[float, float, float]) -> dict:
    ml = logits.argmax(0)
    burn = ml > 0
    phys_sev = 1 + np.digitize(dnbr, (t[1], t[2]))
    fused = np.where(burn, phys_sev, 0)
    keep1 = np.where(burn & (ml == 1) & (phys_sev == 1), 1, fused)
    keep1 = np.where(burn & (ml >= 2) & (phys_sev == 1), ml, keep1)
    return {"ml": ml, "ml_burn_phys_sev": fused, "ml_burn_phys_sev_keep1": keep1}


def run(name: str, files: list[Path]) -> dict:
    folds = fold_of(load_meta())
    thresholds = fold_thresholds()
    per_fold = {m: {v: {} for v in VARIANTS} for m in EVAL_MODES}
    pooled = {
        m: {v: np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64) for v in VARIANTS} for m in EVAL_MODES
    }
    for path in files:
        data = np.load(path)
        ids = [str(x) for x in data["ids"]]
        ks = {folds[c] for c in ids}
        if len(ks) != 1:
            raise ValueError(f"{path} mixes folds {ks}")
        k = ks.pop()
        preds = {v: [] for v in VARIANTS}
        trues, valids = [], {m: [] for m in EVAL_MODES}
        fused_labels = []
        for cid, lg in zip(ids, data["logits"], strict=True):
            raw = load_raw(cid)
            out = fuse(lg.astype(np.float32), spectral_indices(raw.refl)["dnbr"], thresholds[k])
            for v in VARIANTS:
                preds[v].append(out[v].astype(np.uint8))
            fused_labels.append(out["ml_burn_phys_sev"].astype(np.uint8))
            trues.append(raw.mask.astype(np.uint8))
            for m, mode in EVAL_MODES.items():
                valids[m].append(valid_mask(raw.scl_pre, raw.scl_post, raw.refl, mode))
        for m in EVAL_MODES:
            for v in VARIANTS:
                per_fold[m][v][k] = evaluate_scenes(preds[v], trues, valids[m])
                for p, t, vv in zip(preds[v], trues, valids[m], strict=True):
                    pooled[m][v] += confusion(p, t, vv)
        np.savez_compressed(
            OOF_DIR / f"fuse_{name}_f{k}.npz", ids=np.asarray(ids), labels=np.stack(fused_labels)
        )
    return {
        m: {v: summarize_folds(per_fold[m][v], pooled[m][v]) for v in VARIANTS} for m in EVAL_MODES
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("files", nargs="+", type=Path)
    args = p.parse_args()
    result = run(args.name, args.files)
    existing = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    existing[args.name] = result
    OUT_JSON.write_text(json.dumps(existing, indent=2, default=float) + "\n")
    for m, variants in result.items():
        for v, e in variants.items():
            s, pl = e["summary"], e["pooled"]
            print(
                f"{args.name:12s} {m:15s} {v:24s} bs={s['bs_score']['mean']:.4f} "
                f"worst={s['bs_score']['min']:.4f} pooled={pl['bs_score']:.4f} "
                f"iou={[round(x, 3) for x in pl['iou_per_class']]} burn={pl['iou_burn']:.3f}"
            )


if __name__ == "__main__":
    main()
