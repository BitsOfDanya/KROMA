import argparse
import json
import time
from pathlib import Path

import numpy as np
from kroma_ml.af_data import load_chip, load_meta, valid_mask
from kroma_ml.af_features import feature_indices
from kroma_ml.af_split import group_key
from sklearn.model_selection import GroupKFold

ROOT = Path("research/experiments")
FEATURE_GROUPS = ("raw", "thermal", "landcover", "weather", "angles")
TAG = ""


def map_path(name: str, fold: int) -> Path:
    suffix = f"_{TAG}" if TAG else ""
    return ROOT / f"af_cv_{name}{suffix}_{fold}.npz"


def folds():
    meta = load_meta()
    ids = meta["chip_id"].to_numpy()
    groups = group_key(meta).to_numpy()
    for fold, (train_index, val_index) in enumerate(
        GroupKFold(n_splits=3).split(ids, groups=groups), start=1
    ):
        yield fold, meta, ids[train_index].tolist(), ids[val_index].tolist()


def save_maps(name: str, fold: int, ids: list[str], probas, trues, valids) -> None:
    np.savez_compressed(
        map_path(name, fold),
        ids=np.array(ids),
        **{f"proba_{i}": value for i, value in enumerate(probas)},
        **{f"true_{i}": value for i, value in enumerate(trues)},
        **{f"valid_{i}": value for i, value in enumerate(valids)},
    )


def train_lgbm() -> None:
    from af_final_model import mine_hard_negatives
    from kroma_ml.af_features import cached_feature_stack
    from kroma_ml.af_model import predict_chip_proba, sample_training_pixels
    from lightgbm import LGBMClassifier

    index = feature_indices(*FEATURE_GROUPS)
    for fold, meta, train_ids, val_ids in folds():
        started = time.perf_counter()
        hard = mine_hard_negatives(train_ids, meta, index)
        features, labels, _ = sample_training_pixels(
            train_ids, neg_per_chip=400, seed=42,
            extra_negatives=hard, feature_indices=index
        )
        model = LGBMClassifier(
            n_estimators=300, num_leaves=31, learning_rate=0.05,
            class_weight="balanced", random_state=42, verbosity=-1
        )
        model.fit(features, labels)
        probas, trues, valids = [], [], []
        for cid in val_ids:
            chip = load_chip(cid)
            proba, _ = predict_chip_proba(model, cid, index)
            probas.append(proba.astype(np.float32))
            trues.append(chip.mask == 1)
            valids.append(valid_mask(chip))
        save_maps("lgbm", fold, val_ids, probas, trues, valids)
        cached_feature_stack.cache_clear()
        print(
            f"lgbm fold={fold} train={len(train_ids)} val={len(val_ids)} "
            f"seconds={time.perf_counter()-started:.1f}",
            flush=True,
        )


def train_unet() -> None:
    import torch
    from af_unet_experiments import evaluate
    from af_unet_experiments import train_unet as fit
    from kroma_ml.af_features import UNET_CONFIGS, cached_unet_stack
    from kroma_ml.af_torch_data import compute_channel_stats

    names = UNET_CONFIGS["B"]
    for fold, _, train_ids, val_ids in folds():
        started = time.perf_counter()
        stats = compute_channel_stats(train_ids, names)
        model = fit(train_ids, names, "bce_dice", stats, epochs=8, residual=True, val_ids=val_ids)
        probas, trues, valids = evaluate(model, stats, val_ids)
        save_maps("unet", fold, val_ids, probas, trues, valids)
        torch.save(
            {
                "state_dict": model.state_dict(), "channel_names": names,
                "base_channels": 16, "residual": True,
                "normalization_mean": stats.mean, "normalization_std": stats.std,
            },
            ROOT / f"af_cv_unet{('_' + TAG) if TAG else ''}_{fold}.pt",
        )
        cached_unet_stack.cache_clear()
        print(
            f"unet fold={fold} train={len(train_ids)} val={len(val_ids)} "
            f"seconds={time.perf_counter()-started:.1f}",
            flush=True,
        )


def load_maps(name: str, fold: int):
    with np.load(map_path(name, fold)) as data:
        ids = list(data["ids"])
        probas = [data[f"proba_{i}"] for i in range(len(ids))]
        trues = [data[f"true_{i}"] for i in range(len(ids))]
        valids = [data[f"valid_{i}"] for i in range(len(ids))]
    return ids, probas, trues, valids


def tune(probas, trues, valids) -> dict[str, float]:
    positive = np.zeros(1001, dtype=np.int64)
    negative = np.zeros(1001, dtype=np.int64)
    for proba, true, valid in zip(probas, trues, valids, strict=True):
        values = np.clip((proba[valid] * 1000).astype(np.int32), 0, 1000)
        labels = true[valid]
        positive += np.bincount(values[labels], minlength=1001)
        negative += np.bincount(values[~labels], minlength=1001)
    tp = np.cumsum(positive[::-1])[::-1]
    fp = np.cumsum(negative[::-1])[::-1]
    fn = positive.sum() - tp
    denominator = 2 * tp + fp + fn
    f1 = np.divide(
        2 * tp,
        denominator,
        out=np.zeros_like(tp, dtype=float),
        where=denominator > 0,
    )
    coarse = np.arange(50, 951, 50)
    best_coarse = int(coarse[np.argmax(f1[coarse])])
    fine = np.arange(max(5, best_coarse - 50), min(999, best_coarse + 50) + 1, 5)
    if best_coarse >= 900:
        fine = np.arange(max(5, best_coarse - 50), min(999, best_coarse + 50) + 1)
    selected = int(fine[np.argmax(f1[fine])])
    precision = tp[selected] / (tp[selected] + fp[selected]) if tp[selected] + fp[selected] else 0.0
    recall = tp[selected] / (tp[selected] + fn[selected]) if tp[selected] + fn[selected] else 0.0
    return {
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1[selected]), 4),
        "threshold": selected / 1000,
    }


def combine() -> None:
    rows = []
    for fold in range(1, 4):
        l_ids, l_probas, trues, valids = load_maps("lgbm", fold)
        u_ids, u_probas, u_trues, u_valids = load_maps("unet", fold)
        if l_ids != u_ids or any(
            not np.array_equal(left, right)
            for a, b in ((trues, u_trues), (valids, u_valids))
            for left, right in zip(a, b, strict=True)
        ):
            raise ValueError(f"AF CV fold {fold} validation mismatch")
        lgbm = tune(l_probas, trues, valids)
        unet = tune(u_probas, trues, valids)
        candidates = []
        for alpha in np.arange(0, 1.01, 0.1):
            blended = [
                alpha * left + (1 - alpha) * right
                for left, right in zip(l_probas, u_probas, strict=True)
            ]
            candidates.append({"alpha": round(float(alpha), 1), **tune(blended, trues, valids)})
        ensemble = next(row for row in candidates if row["alpha"] == 0.9)
        selected_alpha = max(candidates, key=lambda row: row["f1"])
        rows.append(
            {
                "fold": fold,
                "val_chips": len(l_ids),
                "lgbm": lgbm,
                "unet": unet,
                "ensemble": ensemble,
                "ensemble_selected_alpha": selected_alpha,
            }
        )
        print(
            f"fold={fold} lgbm={lgbm['f1']} unet={unet['f1']} ensemble={ensemble['f1']}",
            flush=True,
        )
    summary = {
        name: {
            "mean_f1": round(float(np.mean([row[name]["f1"] for row in rows])), 4),
            "std_f1": round(float(np.std([row[name]["f1"] for row in rows], ddof=1)), 4),
        }
        for name in ("lgbm", "unet", "ensemble")
    }
    output = {"folds": rows, "summary": summary}
    suffix = f"_{TAG}" if TAG else ""
    (ROOT / f"af_group_cv{suffix}_results.json").write_text(json.dumps(output, indent=2) + "\n")
    print(summary, flush=True)


def lgbm_summary() -> None:
    rows = []
    for fold, _, _, val_ids in folds():
        ids, probas, trues, valids = load_maps("lgbm", fold)
        if ids != val_ids:
            raise ValueError(f"AF CV fold {fold} IDs differ from spatial split")
        metrics = tune(probas, trues, valids)
        rows.append({"fold": fold, "val_chips": len(ids), **metrics})
        print(f"fold={fold} f1={metrics['f1']} threshold={metrics['threshold']}", flush=True)
    result = {
        "tag": TAG,
        "folds": rows,
        "mean_f1": round(float(np.mean([row["f1"] for row in rows])), 4),
        "std_f1": round(float(np.std([row["f1"] for row in rows], ddof=1)), 4),
    }
    suffix = f"_{TAG}" if TAG else ""
    (ROOT / f"af_group_cv_lgbm{suffix}_results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("lgbm", "unet", "combine", "lgbm-summary"))
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    if args.tag and not args.tag.replace("_", "").isalnum():
        parser.error("tag must contain letters, digits or underscores")
    TAG = args.tag
    {"lgbm": train_lgbm, "unet": train_unet, "combine": combine, "lgbm-summary": lgbm_summary}[
        args.mode
    ]()
