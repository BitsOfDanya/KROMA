import time

import numpy as np
from kroma_ml.af_data import load_chip, load_meta, valid_mask
from kroma_ml.af_features import feature_indices
from kroma_ml.af_metrics import Counts, confusion, precision_recall_f1
from kroma_ml.af_model import predict_chip_proba, sample_training_pixels
from kroma_ml.af_postprocess import remove_small_components
from kroma_ml.af_split import group_key, train_val_split
from kroma_ml.af_threshold import sweep
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

NEG_PER_CHIP = 400
SEED = 42


def build_val_truth(val_ids: list[str]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    trues, valids = [], []
    for cid in val_ids:
        chip = load_chip(cid)
        trues.append(chip.mask == 1)
        valids.append(valid_mask(chip))
    return trues, valids


def run_config(
    name: str,
    model_kind: str,
    groups: tuple[str, ...],
    train_ids: list[str],
    val_ids: list[str],
    trues: list[np.ndarray],
    valids: list[np.ndarray],
    extra_negatives: dict | None = None,
    min_component: int = 1,
    results: list[dict] | None = None,
) -> dict:
    idx = feature_indices(*groups)
    t0 = time.time()
    xs, ys, _ = sample_training_pixels(
        train_ids,
        neg_per_chip=NEG_PER_CHIP,
        seed=SEED,
        extra_negatives=extra_negatives,
        feature_indices=idx,
    )
    if model_kind == "logreg":
        scaler = StandardScaler()
        xs_scaled = scaler.fit_transform(xs)
        model = LogisticRegression(max_iter=2000, class_weight="balanced")
        model.fit(xs_scaled, ys)

        class Wrapped:
            def predict_proba(self, x: np.ndarray) -> np.ndarray:
                return model.predict_proba(scaler.transform(x))

        clf = Wrapped()
    else:
        clf = LGBMClassifier(
            n_estimators=300,
            num_leaves=31,
            learning_rate=0.05,
            class_weight="balanced",
            random_state=SEED,
            verbosity=-1,
        )
        clf.fit(xs, ys)
    train_time = time.time() - t0

    t0 = time.time()
    probas = [predict_chip_proba(clf, cid, idx)[0] for cid in val_ids]
    infer_time = time.time() - t0

    best_t, best_f1, _ = sweep(probas, trues, valids)

    total = Counts(0, 0, 0, 0)
    for proba, true, valid in zip(probas, trues, valids, strict=True):
        pred = proba >= best_t
        if min_component > 1:
            pred = remove_small_components(pred.astype(np.uint8), min_component).astype(bool)
        total = total + confusion(pred, true, valid)
    p, r, f1 = precision_recall_f1(total)

    row = {
        "name": name,
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
        "threshold": best_t,
        "train_s": round(train_time, 2),
        "infer_s": round(infer_time, 2),
        "ms_per_chip": round(infer_time / len(val_ids) * 1000, 2),
    }
    print(row)
    if results is not None:
        results.append(row)
    return {"model": clf, "idx": idx, "threshold": best_t, "probas": probas, "row": row}


def mine_hard_negatives(
    train_ids: list[str], meta, idx: np.ndarray, n_folds: int = 3, top_k: int = 20
) -> dict[str, list[tuple[int, int]]]:
    train_meta = meta[meta["chip_id"].isin(train_ids)].reset_index(drop=True)
    groups = group_key(train_meta).to_numpy()
    ids = train_meta["chip_id"].to_numpy()
    n_folds = min(n_folds, len(set(groups)))
    gkf = GroupKFold(n_splits=n_folds)
    hard_negatives: dict[str, list[tuple[int, int]]] = {}
    for fold_train_idx, fold_holdout_idx in gkf.split(ids, groups=groups):
        fold_train_ids = ids[fold_train_idx].tolist()
        fold_holdout_ids = ids[fold_holdout_idx].tolist()
        xs, ys, _ = sample_training_pixels(
            fold_train_ids, neg_per_chip=NEG_PER_CHIP, seed=SEED, feature_indices=idx
        )
        clf = LGBMClassifier(
            n_estimators=200,
            num_leaves=31,
            learning_rate=0.05,
            class_weight="balanced",
            random_state=SEED,
            verbosity=-1,
        )
        clf.fit(xs, ys)
        for cid in fold_holdout_ids:
            chip = load_chip(cid)
            if chip.mask is None:
                continue
            proba, valid = predict_chip_proba(clf, cid, idx)
            pred = proba >= 0.5
            true = chip.mask == 1
            fp = pred & ~true & valid
            ys_fp, xs_fp = np.nonzero(fp)
            if len(ys_fp) == 0:
                continue
            order = np.argsort(-proba[ys_fp, xs_fp])[:top_k]
            hard_negatives[cid] = list(
                zip(ys_fp[order].tolist(), xs_fp[order].tolist(), strict=True)
            )
    return hard_negatives


def main() -> None:
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    train_ids, val_ids = list(train_ids), list(val_ids)
    trues, valids = build_val_truth(val_ids)

    results: list[dict] = []

    run_config(
        "ml_raw_logreg", "logreg", ("raw",), train_ids, val_ids, trues, valids, results=results
    )
    run_config(
        "ml_raw_thermal_logreg",
        "logreg",
        ("raw", "thermal"),
        train_ids,
        val_ids,
        trues,
        valids,
        results=results,
    )
    run_config(
        "ml_raw_thermal_landcover_logreg",
        "logreg",
        ("raw", "thermal", "landcover"),
        train_ids,
        val_ids,
        trues,
        valids,
        results=results,
    )
    run_config(
        "ml_raw_thermal_landcover_weather_logreg",
        "logreg",
        ("raw", "thermal", "landcover", "weather"),
        train_ids,
        val_ids,
        trues,
        valids,
        results=results,
    )
    full_groups = ("raw", "thermal", "landcover", "weather", "angles")
    run_config(
        "ml_full_logreg", "logreg", full_groups, train_ids, val_ids, trues, valids, results=results
    )
    base = run_config(
        "ml_full_lgbm", "lgbm", full_groups, train_ids, val_ids, trues, valids, results=results
    )

    idx = base["idx"]
    hard_negatives = mine_hard_negatives(train_ids, meta, idx)
    n_hard = sum(len(v) for v in hard_negatives.values())
    print(f"mined {n_hard} out-of-fold hard negatives from {len(hard_negatives)} train chips")

    hn_train = run_config(
        "ml_full_lgbm_hardneg",
        "lgbm",
        full_groups,
        train_ids,
        val_ids,
        trues,
        valids,
        extra_negatives=hard_negatives,
        results=results,
    )

    for min_size in (1, 2, 3, 4):
        probas = hn_train["probas"]
        best_t = hn_train["threshold"]
        total = Counts(0, 0, 0, 0)
        for proba, true, valid in zip(probas, trues, valids, strict=True):
            pred = proba >= best_t
            if min_size > 1:
                pred = remove_small_components(pred.astype(np.uint8), min_size).astype(bool)
            total = total + confusion(pred, true, valid)
        p, r, f1 = precision_recall_f1(total)
        row = {
            "name": f"postprocess_min_component_{min_size}",
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
        }
        print(row)
        results.append(row)

    print("\n=== ABLATION TABLE ===")
    for row in results:
        print(row)


if __name__ == "__main__":
    main()
