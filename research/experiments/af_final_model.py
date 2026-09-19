import time

import joblib
import numpy as np
from kroma_ml.af_data import load_chip, load_meta
from kroma_ml.af_features import feature_indices
from kroma_ml.af_metrics import Counts, confusion, precision_recall_f1
from kroma_ml.af_model import predict_chip_proba, sample_training_pixels
from kroma_ml.af_split import group_key, train_val_split
from kroma_ml.af_threshold import sweep
from lightgbm import LGBMClassifier

SEED = 42
NEG_PER_CHIP = 400
FULL_GROUPS = ("raw", "thermal", "landcover", "weather", "angles")


def mine_hard_negatives(train_ids, meta, idx, n_folds=3, top_k=20):
    from sklearn.model_selection import GroupKFold

    train_meta = meta[meta["chip_id"].isin(train_ids)].reset_index(drop=True)
    groups = group_key(train_meta).to_numpy()
    ids = train_meta["chip_id"].to_numpy()
    n_folds = min(n_folds, len(set(groups)))
    gkf = GroupKFold(n_splits=n_folds)
    hard_negatives = {}
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
    idx = feature_indices(*FULL_GROUPS)

    hard_negatives = mine_hard_negatives(train_ids, meta, idx)

    t0 = time.time()
    xs, ys, _ = sample_training_pixels(
        train_ids,
        neg_per_chip=NEG_PER_CHIP,
        seed=SEED,
        extra_negatives=hard_negatives,
        feature_indices=idx,
    )
    clf = LGBMClassifier(
        n_estimators=300,
        num_leaves=31,
        learning_rate=0.05,
        class_weight="balanced",
        random_state=SEED,
        verbosity=-1,
    )
    clf.fit(xs, ys)
    print(
        "train time",
        round(time.time() - t0, 2),
        "s, n_train_px",
        len(ys),
        "positives",
        int(ys.sum()),
    )

    trues, valids, probas = [], [], []
    t0 = time.time()
    for cid in val_ids:
        chip = load_chip(cid)
        proba, valid = predict_chip_proba(clf, cid, idx)
        trues.append(chip.mask == 1)
        valids.append(valid)
        probas.append(proba)
    infer_time = time.time() - t0
    print(
        f"val inference {infer_time:.2f}s for {len(val_ids)} chips ({infer_time / len(val_ids) * 1000:.2f} ms/chip)"
    )

    grid = np.arange(0.3, 0.995, 0.02)
    best_t, best_f1, results = sweep(probas, trues, valids, grid=grid)
    print("best threshold", round(best_t, 3), "f1", round(best_f1, 4))

    total = Counts(0, 0, 0, 0)
    for proba, true, valid in zip(probas, trues, valids, strict=True):
        total = total + confusion(proba >= best_t, true, valid)
    p, r, f1 = precision_recall_f1(total)
    print(f"FINAL VAL precision={p:.4f} recall={r:.4f} f1={f1:.4f} threshold={best_t:.3f}")

    by_sat = {}
    for cid in val_ids:
        sat = meta.loc[meta["chip_id"] == cid, "satellite"].iloc[0]
        by_sat.setdefault(sat, []).append(cid)
    print("\n=== PER-SATELLITE VAL F1 ===")
    for sat, ids_ in by_sat.items():
        total_s = Counts(0, 0, 0, 0)
        for cid in ids_:
            chip = load_chip(cid)
            proba, valid = predict_chip_proba(clf, cid, idx)
            total_s = total_s + confusion(proba >= best_t, chip.mask == 1, valid)
        p_, r_, f1_ = precision_recall_f1(total_s)
        print(
            sat,
            "n_chips",
            len(ids_),
            "precision",
            round(p_, 4),
            "recall",
            round(r_, 4),
            "f1",
            round(f1_, 4),
        )

    joblib.dump(
        {"model": clf, "feature_indices": idx, "threshold": best_t},
        "research/experiments/af_final_model.joblib",
    )
    print("saved model to research/experiments/af_final_model.joblib")


if __name__ == "__main__":
    main()
