from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from kroma_ml.af_split import group_key
from kroma_ml.bs_data import SCL_INVALID_STRICT
from kroma_ml.bs_metrics import NUM_CLASSES, evaluate_predictions

N_FOLDS = 3
TRUE_INVALID = frozenset({0, 1})
MASK_MODES = ("strict", "true", "none")
EVAL_MODES = {"strict_mask": "strict", "all_valid_mask": "true"}
CLASS_ORDER = ("background", "low", "moderate", "high")
SCENE_SHAPE = (512, 512)


def fold_ids(meta: pd.DataFrame, n_folds: int = N_FOLDS) -> list[tuple[list[str], list[str]]]:
    ids = meta["chip_id"].to_numpy()
    splits = GroupKFold(n_splits=n_folds).split(ids, groups=group_key(meta).to_numpy())
    return [(ids[tr].tolist(), ids[va].tolist()) for tr, va in splits]


def fold_of(meta: pd.DataFrame, n_folds: int = N_FOLDS) -> dict[str, int]:
    return {cid: k + 1 for k, (_, va) in enumerate(fold_ids(meta, n_folds)) for cid in va}


def impossible_pixels(refl: np.ndarray) -> np.ndarray:
    bad = ~np.isfinite(refl).all(0)
    bad |= (refl[:4] <= 0).all(0) | (refl[4:] <= 0).all(0)
    return bad


def valid_mask(
    scl_pre: np.ndarray, scl_post: np.ndarray, refl: np.ndarray, mode: str
) -> np.ndarray:
    if mode == "none":
        return ~impossible_pixels(refl)
    if mode not in ("strict", "true"):
        raise ValueError(mode)
    codes = list(SCL_INVALID_STRICT if mode == "strict" else TRUE_INVALID)
    return ~(np.isin(scl_pre, codes) | np.isin(scl_post, codes))


def confusion(pred: np.ndarray, true: np.ndarray, valid: np.ndarray) -> np.ndarray:
    idx = true[valid].astype(np.int64) * NUM_CLASSES + pred[valid].astype(np.int64)
    return np.bincount(idx, minlength=NUM_CLASSES**2).reshape(NUM_CLASSES, NUM_CLASSES)


def metrics_from_confusion(cm: np.ndarray) -> dict:
    cm = np.asarray(cm, dtype=np.float64)
    tp = np.diag(cm)
    pred_n, true_n = cm.sum(0), cm.sum(1)
    union = pred_n + true_n - tp
    iou = np.divide(tp, union, out=np.full(NUM_CLASSES, np.nan), where=union > 0)
    precision = np.divide(tp, pred_n, out=np.zeros(NUM_CLASSES), where=pred_n > 0)
    recall = np.divide(tp, true_n, out=np.zeros(NUM_CLASSES), where=true_n > 0)
    denom = precision + recall
    f1 = np.divide(2 * precision * recall, denom, out=np.zeros(NUM_CLASSES), where=denom > 0)
    burn_tp = cm[1:, 1:].sum()
    burn_union = cm[1:].sum() + cm[:, 1:].sum() - burn_tp
    iou_burn = float(burn_tp / burn_union) if burn_union > 0 else 0.0
    miou_sev = float(np.nanmean(iou[1:]))
    row = np.maximum(true_n, 1)[:, None]
    return {
        "bs_score": 0.35 * iou_burn + 0.30 * miou_sev,
        "iou_burn": iou_burn,
        "miou_severity": miou_sev,
        "miou_all": float(np.nanmean(iou)),
        "iou_per_class": iou.tolist(),
        "precision_per_class": precision.tolist(),
        "recall_per_class": recall.tolist(),
        "f1_per_class": f1.tolist(),
        "row_normalized": (cm / row).round(4).tolist(),
        "confusion": cm.astype(np.int64).tolist(),
    }


def evaluate_scenes(
    preds: list[np.ndarray], trues: list[np.ndarray], valids: list[np.ndarray]
) -> dict:
    cm = sum(
        (confusion(p, t, v) for p, t, v in zip(preds, trues, valids, strict=True)),
        np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64),
    )
    out = metrics_from_confusion(cm)
    official = evaluate_predictions(preds, trues, valids)
    if not np.isclose(official["bs_score"], out["bs_score"], atol=1e-9):
        raise RuntimeError("evaluator mismatch")
    out["bs_score"] = official["bs_score"]
    return out


def summarize_folds(per_fold: dict[int, dict], pooled_cm: np.ndarray) -> dict:
    keys = ("bs_score", "iou_burn", "miou_severity", "miou_all")
    folds = sorted(per_fold)
    summary = {}
    for key in keys:
        vals = np.array([per_fold[f][key] for f in folds])
        summary[key] = {
            "mean": float(vals.mean()),
            "std": float(vals.std()),
            "min": float(vals.min()),
        }
    for c in range(NUM_CLASSES):
        for key in ("iou_per_class", "precision_per_class", "recall_per_class", "f1_per_class"):
            vals = np.array([per_fold[f][key][c] for f in folds])
            summary[f"{key[:-10]}_{c}"] = {"mean": float(vals.mean()), "std": float(vals.std())}
    worst = min(folds, key=lambda f: per_fold[f]["bs_score"])
    return {
        "folds": {str(f): per_fold[f] for f in folds},
        "summary": summary,
        "worst_fold": worst,
        "pooled": metrics_from_confusion(pooled_cm),
    }


def save_predictions(path: Path, ids: list[str], logits: np.ndarray) -> None:
    if logits.ndim != 4 or logits.shape[1] != NUM_CLASSES:
        raise ValueError(f"logits must be (N,{NUM_CLASSES},H,W), got {logits.shape}")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        ids=np.asarray(ids),
        logits=logits.astype(np.float16),
        class_order=np.asarray(CLASS_ORDER),
    )


def load_predictions(path: Path) -> tuple[list[str], np.ndarray]:
    data = np.load(path, allow_pickle=False)
    ids = [str(x) for x in data["ids"]]
    if "class_order" in data and tuple(str(x) for x in data["class_order"]) != CLASS_ORDER:
        raise ValueError(f"class_order must be {CLASS_ORDER}")
    if "logits" in data:
        arr = data["logits"].astype(np.float32)
        if arr.ndim != 4 or arr.shape[1] != NUM_CLASSES:
            raise ValueError(f"logits must be (N,{NUM_CLASSES},H,W), got {arr.shape}")
        labels = arr.argmax(1)
    elif "probs" in data:
        arr = data["probs"].astype(np.float32)
        if arr.ndim != 4 or arr.shape[1] != NUM_CLASSES:
            raise ValueError(f"probs must be (N,{NUM_CLASSES},H,W), got {arr.shape}")
        labels = arr.argmax(1)
    elif "labels" in data:
        labels = data["labels"].astype(np.int64)
        if labels.ndim != 3 or labels.min() < 0 or labels.max() >= NUM_CLASSES:
            raise ValueError("labels must be (N,H,W) with values in 0..3")
    else:
        raise ValueError("npz needs one of: logits, probs, labels")
    if len(ids) != len(labels) or len(set(ids)) != len(ids):
        raise ValueError("ids must be unique and match the first axis")
    if labels.shape[1:] != SCENE_SHAPE:
        raise ValueError(f"scene shape must be {SCENE_SHAPE}, got {labels.shape[1:]}")
    return ids, labels
