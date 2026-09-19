import json

import joblib
import numpy as np
from kroma_ml.af_data import load_chip, load_meta, valid_mask
from kroma_ml.af_metrics import Counts, confusion, precision_recall_f1
from kroma_ml.af_model import predict_chip_proba
from kroma_ml.af_split import train_val_split
from kroma_ml.af_threshold import sweep

LGBM_PATH = "research/experiments/af_final_model.joblib"
UNET_PROBAS_PATH = "research/experiments/af_unet_val_probas.npz"
UNET_RESULTS_PATH = "research/experiments/af_unet_results.json"


def blend_probabilities(lgbm: np.ndarray, unet: np.ndarray, alpha: float) -> np.ndarray:
    if not 0 <= alpha <= 1 or lgbm.shape != unet.shape:
        raise ValueError("ensemble weights and probability shapes must match")
    return alpha * lgbm + (1 - alpha) * unet


def load_unet_val() -> tuple[list[str], list[np.ndarray], list[np.ndarray], list[np.ndarray]]:
    data = np.load(UNET_PROBAS_PATH, allow_pickle=True)
    val_ids = list(data["val_ids"])
    n = len(val_ids)
    probas = [data[f"proba_{i}"] for i in range(n)]
    trues = [data[f"true_{i}"] for i in range(n)]
    valids = [data[f"valid_{i}"] for i in range(n)]
    return val_ids, probas, trues, valids


def main() -> None:
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    val_ids = list(val_ids)

    bundle = joblib.load(LGBM_PATH)
    lgbm_model, lgbm_idx = bundle["model"], bundle["feature_indices"]

    unet_val_ids, unet_probas, unet_trues, unet_valids = load_unet_val()
    assert unet_val_ids == val_ids, "val split mismatch between LightGBM and U-Net runs"

    lgbm_probas, trues, valids = [], [], []
    for cid in val_ids:
        chip = load_chip(cid)
        proba, valid = predict_chip_proba(lgbm_model, cid, lgbm_idx)
        lgbm_probas.append(proba)
        trues.append(chip.mask == 1)
        valids.append(valid_mask(chip))

    for cid, true, valid, unet_true, unet_valid in zip(
        val_ids, trues, valids, unet_trues, unet_valids, strict=True
    ):
        if not np.array_equal(true, unet_true) or not np.array_equal(valid, unet_valid):
            raise ValueError(f"validation mask mismatch for {cid}")

    def eval_probas(probas: list[np.ndarray]) -> dict:
        coarse_t, _, _ = sweep(probas, trues, valids)
        fine_grid = np.arange(
            max(0.005, coarse_t - 0.05), min(0.995, coarse_t + 0.05) + 0.0001, 0.005
        )
        best_t, _, _ = sweep(probas, trues, valids, grid=fine_grid)
        total = Counts(0, 0, 0, 0)
        for proba, true, valid in zip(probas, trues, valids, strict=True):
            total = total + confusion(proba >= best_t, true, valid)
        p, r, f1 = precision_recall_f1(total)
        return {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "threshold": round(best_t, 3),
        }

    lgbm_metrics = eval_probas(lgbm_probas)
    unet_metrics = eval_probas(unet_probas)
    print("LightGBM alone:", lgbm_metrics)
    print("U-Net alone   :", unet_metrics)

    best_alpha, best_f1, best_metrics = None, -1.0, None
    sweep_rows = []
    for alpha in np.linspace(0.0, 1.0, 11):
        blended = [
            blend_probabilities(lg, un, float(alpha))
            for lg, un in zip(lgbm_probas, unet_probas, strict=True)
        ]
        metrics = eval_probas(blended)
        sweep_rows.append({"alpha": round(float(alpha), 2), **metrics})
        if metrics["f1"] > best_f1:
            best_f1, best_alpha, best_metrics = metrics["f1"], float(alpha), metrics

    print("\n=== ALPHA SWEEP ===")
    for row in sweep_rows:
        print(row)
    print(f"\nBEST ENSEMBLE alpha={best_alpha} {best_metrics}")
    print(f"gain over LightGBM alone: {best_metrics['f1'] - lgbm_metrics['f1']:+.4f}")
    print(f"gain over U-Net alone: {best_metrics['f1'] - unet_metrics['f1']:+.4f}")

    lgbm_pred = [p >= lgbm_metrics["threshold"] for p in lgbm_probas]
    unet_pred = [p >= unet_metrics["threshold"] for p in unet_probas]

    both_fp = both_fn = only_lgbm_fp = only_unet_fp = only_lgbm_fn = only_unet_fn = 0
    for lp, up, true, valid in zip(lgbm_pred, unet_pred, trues, valids, strict=True):
        lgbm_fp = lp & ~true & valid
        unet_fp = up & ~true & valid
        lgbm_fn = ~lp & true & valid
        unet_fn = ~up & true & valid
        both_fp += int((lgbm_fp & unet_fp).sum())
        only_lgbm_fp += int((lgbm_fp & ~unet_fp).sum())
        only_unet_fp += int((unet_fp & ~lgbm_fp).sum())
        both_fn += int((lgbm_fn & unet_fn).sum())
        only_lgbm_fn += int((lgbm_fn & ~unet_fn).sum())
        only_unet_fn += int((unet_fn & ~lgbm_fn).sum())

    print("\n=== ERROR OVERLAP (pixel counts on val) ===")
    print("FP both:", both_fp, "FP only LightGBM:", only_lgbm_fp, "FP only U-Net:", only_unet_fp)
    print("FN both:", both_fn, "FN only LightGBM:", only_lgbm_fn, "FN only U-Net:", only_unet_fn)

    with open("research/experiments/af_ensemble_results.json", "w") as f:
        json.dump(
            {
                "lgbm": lgbm_metrics,
                "unet": unet_metrics,
                "best_ensemble": {"alpha": best_alpha, **best_metrics},
                "alpha_sweep": sweep_rows,
                "error_overlap": {
                    "fp_both": both_fp,
                    "fp_only_lgbm": only_lgbm_fp,
                    "fp_only_unet": only_unet_fp,
                    "fn_both": both_fn,
                    "fn_only_lgbm": only_lgbm_fn,
                    "fn_only_unet": only_unet_fn,
                },
            },
            f,
            indent=2,
        )
    print("\nsaved research/experiments/af_ensemble_results.json")


if __name__ == "__main__":
    main()
