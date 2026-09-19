import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from kroma_ml.af_split import group_key
from kroma_ml.bs_data import SCL_INVALID_STRICT, load_chip, load_meta, valid_mask
from kroma_ml.bs_features import BS_CONFIGS, cached_bs_stack
from kroma_ml.bs_losses import BurnSeverityLoss, CombinedLoss
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_model import AttentionUNet
from kroma_ml.bs_torch_data import BSChipDataset, class_weights, compute_channel_stats, normalize
from sklearn.model_selection import GroupKFold
from torch.utils.data import DataLoader

ROOT = Path("research/experiments")
DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
SEED = 42
BATCH_SIZE = 4
BASE_CHANNELS = 32
CONFIG_NAME = "B"
N_FOLDS = 3


def folds(n_splits: int = N_FOLDS):
    meta = load_meta()
    ids = meta["chip_id"].to_numpy()
    groups = group_key(meta).to_numpy()
    gkf = GroupKFold(n_splits=n_splits)
    for fold, (train_idx, val_idx) in enumerate(gkf.split(ids, groups=groups), start=1):
        yield fold, ids[train_idx].tolist(), ids[val_idx].tolist()


def make_criterion(loss_name: str, weights: torch.Tensor):
    if loss_name == "combined":
        return CombinedLoss(class_weights=weights, num_classes=4)
    if loss_name == "hierarchical":
        return BurnSeverityLoss(class_weights=weights[1:])
    raise ValueError(f"unknown BS loss: {loss_name}")


def train_fold(train_ids: list[str], epochs: int, names: tuple[str, ...], loss_name: str):
    torch.manual_seed(SEED)
    stats = compute_channel_stats(train_ids, names, SCL_INVALID_STRICT)
    weights = class_weights(train_ids, invalid_codes=SCL_INVALID_STRICT).to(DEVICE)
    train_ds = BSChipDataset(train_ids, stats, augment=True, invalid_codes=SCL_INVALID_STRICT)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)

    model = AttentionUNet(in_channels=len(names), base=BASE_CHANNELS).to(DEVICE)
    optimizer = torch.optim.SGD(
        model.parameters(), lr=1e-3, momentum=0.9, weight_decay=1e-4, nesterov=True
    )
    criterion = make_criterion(loss_name, weights)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad(set_to_none=True)
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step()
        print(f"  epoch {epoch + 1}/{epochs} loss={epoch_loss / len(train_loader):.4f}", flush=True)
    return model, stats


def collect_logits(model, stats, chip_ids: list[str]):
    model.eval()
    logits_list, trues, valids = [], [], []
    with torch.no_grad():
        for cid in chip_ids:
            chip = load_chip(cid)
            stack = normalize(cached_bs_stack(cid, stats.names), stats)
            x = torch.from_numpy(stack.transpose(2, 0, 1)).float().unsqueeze(0).to(DEVICE)
            logits = model(x).squeeze(0).cpu().numpy()
            logits_list.append(logits)
            trues.append(chip.mask.astype(np.int64))
            valids.append(valid_mask(chip, SCL_INVALID_STRICT))
    return logits_list, trues, valids


def score_with_bias(logits_list, trues, valids, bias: np.ndarray) -> dict:
    preds = [
        (logits + bias[:, None, None]).argmax(axis=0).astype(np.int64) for logits in logits_list
    ]
    return evaluate_predictions(preds, trues, valids)


def coordinate_calibrate(logits_list, trues, valids) -> tuple[np.ndarray, dict]:
    grid = np.arange(-4.0, 0.05, 0.2)
    best_bias = np.zeros(4)
    best_score = score_with_bias(logits_list, trues, valids, best_bias)["bs_score"]
    for _ in range(3):
        improved = False
        for class_id in (1, 2, 3):
            for value in grid:
                candidate = best_bias.copy()
                candidate[class_id] = value
                result = score_with_bias(logits_list, trues, valids, candidate)
                if result["bs_score"] > best_score:
                    best_score = result["bs_score"]
                    best_bias = candidate
                    improved = True
        if not improved:
            break
    return best_bias, score_with_bias(logits_list, trues, valids, best_bias)


def run(epochs: int = 10, tag: str = "", loss_name: str = "combined") -> dict:
    names = BS_CONFIGS[CONFIG_NAME]
    fold_rows = []
    oof_logits, oof_trues, oof_valids = [], [], []
    started = time.perf_counter()
    for fold, train_ids, val_ids in folds():
        print(f"fold {fold}: train={len(train_ids)} val={len(val_ids)}", flush=True)
        model, stats = train_fold(train_ids, epochs, names, loss_name)
        logits_list, trues, valids = collect_logits(model, stats, val_ids)
        raw = evaluate_predictions([logits.argmax(axis=0) for logits in logits_list], trues, valids)
        bias, calibrated = coordinate_calibrate(logits_list, trues, valids)
        fold_rows.append(
            {
                "fold": fold,
                "val_chips": len(val_ids),
                "raw": raw,
                "fold_calibrated": calibrated,
                "fold_bias": bias.tolist(),
            }
        )
        oof_logits.extend(logits_list)
        oof_trues.extend(trues)
        oof_valids.extend(valids)
        print(
            f"fold {fold} raw={raw['bs_score']:.4f} calibrated={calibrated['bs_score']:.4f}",
            flush=True,
        )

    global_bias, global_calibrated = coordinate_calibrate(oof_logits, oof_trues, oof_valids)
    global_raw = evaluate_predictions(
        [logits.argmax(axis=0) for logits in oof_logits], oof_trues, oof_valids
    )

    def mean_std(key: str, subkey: str) -> dict:
        values = [row[key][subkey] for row in fold_rows]
        return {
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values, ddof=1)), 4),
        }

    summary = {
        "raw": {k: mean_std("raw", k) for k in ("iou_burn", "miou_severity", "bs_score")},
        "fold_calibrated": {
            k: mean_std("fold_calibrated", k) for k in ("iou_burn", "miou_severity", "bs_score")
        },
    }
    result = {
        "config": CONFIG_NAME,
        "loss": loss_name,
        "channel_names": list(names),
        "epochs": epochs,
        "n_folds": N_FOLDS,
        "folds": fold_rows,
        "summary": summary,
        "oof_global_bias": global_bias.tolist(),
        "oof_global_calibrated": global_calibrated,
        "oof_raw": global_raw,
        "total_seconds": round(time.perf_counter() - started, 1),
    }
    suffix = f"_{tag}" if tag else ""
    (ROOT / f"bs_group_cv{suffix}_results.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--tag", default="")
    parser.add_argument("--loss", choices=("combined", "hierarchical"), default="combined")
    args = parser.parse_args()
    print(json.dumps(run(epochs=args.epochs, tag=args.tag, loss_name=args.loss), indent=2))


if __name__ == "__main__":
    main()
