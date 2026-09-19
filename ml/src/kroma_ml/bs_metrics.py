import numpy as np

NUM_CLASSES = 4


def confusion_counts(pred: np.ndarray, true: np.ndarray, valid: np.ndarray) -> np.ndarray:
    intersection = np.zeros(NUM_CLASSES)
    union = np.zeros(NUM_CLASSES)
    for c in range(NUM_CLASSES):
        pred_c = (pred == c) & valid
        true_c = (true == c) & valid
        intersection[c] += (pred_c & true_c).sum()
        union[c] += (pred_c | true_c).sum()
    return np.stack([intersection, union])


def iou_from_counts(intersection: np.ndarray, union: np.ndarray) -> np.ndarray:
    return np.divide(intersection, union, out=np.full_like(intersection, np.nan), where=union > 0)


def bs_scores(iou_per_class: np.ndarray, burn_intersection: float, burn_union: float) -> dict:
    miou_severity = float(np.nanmean(iou_per_class[1:]))
    iou_burn = float(burn_intersection / burn_union) if burn_union > 0 else 0.0
    return {
        "iou_per_class": [float(x) for x in iou_per_class],
        "iou_burn": iou_burn,
        "miou_severity": miou_severity,
        "miou_all": float(np.nanmean(iou_per_class)),
        "bs_score": 0.35 * iou_burn + 0.30 * miou_severity,
    }


def evaluate_predictions(
    preds: list[np.ndarray], trues: list[np.ndarray], valids: list[np.ndarray]
) -> dict:
    intersection = np.zeros(NUM_CLASSES)
    union = np.zeros(NUM_CLASSES)
    burn_intersection = 0.0
    burn_union = 0.0
    for pred, true, valid in zip(preds, trues, valids, strict=True):
        counts = confusion_counts(pred, true, valid)
        intersection += counts[0]
        union += counts[1]
        pred_burn = (pred > 0) & valid
        true_burn = (true > 0) & valid
        burn_intersection += (pred_burn & true_burn).sum()
        burn_union += (pred_burn | true_burn).sum()
    iou_per_class = iou_from_counts(intersection, union)
    return bs_scores(iou_per_class, burn_intersection, burn_union)
