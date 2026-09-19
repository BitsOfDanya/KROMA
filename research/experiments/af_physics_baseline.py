import itertools
import time

import numpy as np
from kroma_ml.af_data import load_chip, load_meta, valid_mask
from kroma_ml.af_metrics import Counts, confusion, precision_recall_f1
from kroma_ml.af_physics import PhysicsParams, physics_signals
from kroma_ml.af_split import train_val_split

WINDOW = 7
I4_GRID = np.arange(300, 345, 3)
DIFF_GRID = np.arange(0, 40, 3)
ANOM_GRID = np.arange(-10, 30, 3)


def cache_chip(chip_id: str) -> dict:
    chip = load_chip(chip_id)
    i4, diff, anom = physics_signals(chip, WINDOW)
    return {
        "i4": i4,
        "diff": diff,
        "anom": anom,
        "true": (chip.mask == 1),
        "valid": valid_mask(chip),
    }


def evaluate(cache: list[dict], params: PhysicsParams) -> Counts:
    total = Counts(0, 0, 0, 0)
    for item in cache:
        pred = (
            (item["i4"] > params.i4_min)
            & (item["diff"] > params.diff_min)
            & (item["anom"] > params.anom_min)
        )
        total = total + confusion(pred, item["true"], item["valid"])
    return total


def main() -> None:
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    print("train chips:", len(train_ids), "val chips:", len(val_ids))

    t0 = time.time()
    train_cache = [cache_chip(cid) for cid in train_ids]
    val_cache = [cache_chip(cid) for cid in val_ids]
    print("cache built in", round(time.time() - t0, 1), "s")

    best = None
    combos = list(itertools.product(I4_GRID, DIFF_GRID, ANOM_GRID))
    t0 = time.time()
    for i4_min, diff_min, anom_min in combos:
        params = PhysicsParams(float(i4_min), float(diff_min), float(anom_min), WINDOW)
        counts = evaluate(train_cache, params)
        _, _, f1 = precision_recall_f1(counts)
        if best is None or f1 > best[0]:
            best = (f1, params, counts)
    print("grid search over", len(combos), "combos took", round(time.time() - t0, 1), "s")

    f1_train, params, counts_train = best
    p, r, f1 = precision_recall_f1(counts_train)
    print(f"BEST TRAIN params={params} precision={p:.4f} recall={r:.4f} f1={f1:.4f}")

    t0 = time.time()
    counts_val = evaluate(val_cache, params)
    infer_time = time.time() - t0
    p, r, f1 = precision_recall_f1(counts_val)
    print(f"VAL with train-tuned params: precision={p:.4f} recall={r:.4f} f1={f1:.4f}")
    print(
        f"val inference time for {len(val_cache)} chips: {infer_time:.3f}s ({infer_time / len(val_cache) * 1000:.2f} ms/chip)"
    )

    best_val = None
    for i4_min, diff_min, anom_min in combos:
        p2 = PhysicsParams(float(i4_min), float(diff_min), float(anom_min), WINDOW)
        counts = evaluate(val_cache, p2)
        _, _, f1v = precision_recall_f1(counts)
        if best_val is None or f1v > best_val[0]:
            best_val = (f1v, p2, counts)
    print(f"ORACLE (tuned directly on val) f1={best_val[0]:.4f} params={best_val[1]}")


if __name__ == "__main__":
    main()
