import numpy as np

from kroma_ml.af_metrics import Counts, confusion, precision_recall_f1


def sweep(
    proba_list: list[np.ndarray],
    true_list: list[np.ndarray],
    valid_list: list[np.ndarray],
    grid: np.ndarray | None = None,
) -> tuple[float, float, dict[float, tuple[float, float, float]]]:
    if grid is None:
        grid = np.arange(0.05, 1.0, 0.05)
    results: dict[float, tuple[float, float, float]] = {}
    best_t, best_f1 = 0.5, -1.0
    for t in grid:
        total = Counts(0, 0, 0, 0)
        for proba, true, valid in zip(proba_list, true_list, valid_list, strict=True):
            pred = proba >= t
            total = total + confusion(pred, true, valid)
        p, r, f1 = precision_recall_f1(total)
        results[float(t)] = (p, r, f1)
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return best_t, best_f1, results
