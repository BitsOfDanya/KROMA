from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Counts:
    tp: int
    fp: int
    fn: int
    tn: int

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(
            self.tp + other.tp, self.fp + other.fp, self.fn + other.fn, self.tn + other.tn
        )


def confusion(pred: np.ndarray, true: np.ndarray, valid: np.ndarray | None = None) -> Counts:
    pred = pred.astype(bool)
    true = true.astype(bool)
    if valid is not None:
        valid = valid.astype(bool)
        pred = pred & valid
        true = true & valid
    else:
        valid = np.ones_like(pred, dtype=bool)
    tp = int(np.sum(pred & true))
    fp = int(np.sum(pred & ~true & valid))
    fn = int(np.sum(~pred & true))
    tn = int(np.sum(~pred & ~true & valid))
    return Counts(tp, fp, fn, tn)


def precision_recall_f1(counts: Counts) -> tuple[float, float, float]:
    precision = counts.tp / (counts.tp + counts.fp) if (counts.tp + counts.fp) > 0 else 0.0
    recall = counts.tp / (counts.tp + counts.fn) if (counts.tp + counts.fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def f1_from_arrays(pred: np.ndarray, true: np.ndarray, valid: np.ndarray | None = None) -> float:
    return precision_recall_f1(confusion(pred, true, valid))[2]
