import argparse
import json
from pathlib import Path

import numpy as np
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import (
    EVAL_MODES,
    N_FOLDS,
    confusion,
    evaluate_scenes,
    fold_of,
    load_predictions,
    summarize_folds,
    valid_mask,
)
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_metrics import NUM_CLASSES


def evaluate_files(files: list[Path], modes: dict[str, str] = EVAL_MODES) -> dict:
    meta = load_meta()
    folds = fold_of(meta)
    per_fold = {m: {} for m in modes}
    pooled = {m: np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64) for m in modes}
    seen: set[str] = set()
    by_fold: dict[int, list] = {k: [] for k in range(1, N_FOLDS + 1)}
    for path in files:
        ids, labels = load_predictions(path)
        dup = seen & set(ids)
        if dup:
            raise ValueError(f"duplicate chips across files: {sorted(dup)[:5]}")
        seen |= set(ids)
        unknown = [c for c in ids if c not in folds]
        if unknown:
            raise ValueError(f"unknown chip ids: {unknown[:5]}")
        for cid, pred in zip(ids, labels, strict=True):
            by_fold[folds[cid]].append((cid, pred.astype(np.uint8)))
    for k, items in by_fold.items():
        if not items:
            continue
        raws = [load_raw(cid) for cid, _ in items]
        preds = [p for _, p in items]
        trues = [r.mask.astype(np.uint8) for r in raws]
        for name, mode in modes.items():
            valids = [valid_mask(r.scl_pre, r.scl_post, r.refl, mode) for r in raws]
            per_fold[name][k] = evaluate_scenes(preds, trues, valids)
            for p, t, v in zip(preds, trues, valids, strict=True):
                pooled[name] += confusion(p, t, v)
    coverage = len(seen) / len(meta)
    out = {"chips": len(seen), "coverage": coverage, "files": [str(f) for f in files]}
    for name in modes:
        out[name] = summarize_folds(per_fold[name], pooled[name])
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--json", type=Path, default=None)
    args = p.parse_args()
    result = evaluate_files(args.files)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(f"chips={result['chips']} coverage={result['coverage']:.3f}")
    for name in EVAL_MODES:
        s, pooled = result[name]["summary"], result[name]["pooled"]
        print(
            f"{name:15s} bs_mean={s['bs_score']['mean']:.4f}±{s['bs_score']['std']:.4f} "
            f"worst={s['bs_score']['min']:.4f} pooled={pooled['bs_score']:.4f} "
            f"burn={pooled['iou_burn']:.3f} miou={pooled['miou_all']:.3f} "
            f"iou={[round(x, 3) for x in pooled['iou_per_class']]} "
            f"P1={pooled['precision_per_class'][1]:.3f} R1={pooled['recall_per_class'][1]:.3f} "
            f"F1_1={pooled['f1_per_class'][1]:.3f}"
        )


if __name__ == "__main__":
    main()
