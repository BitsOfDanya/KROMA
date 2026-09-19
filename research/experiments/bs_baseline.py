import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_data import SCL_INVALID_LOOSE, SCL_INVALID_STRICT, load_chip, load_meta, valid_mask
from kroma_ml.bs_features import BS_CONFIGS, cached_bs_stack
from kroma_ml.bs_losses import BurnSeverityLoss, CombinedLoss
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_model import AttentionUNet, count_parameters
from kroma_ml.bs_torch_data import BSChipDataset, class_weights, compute_channel_stats, normalize
from torch.utils.data import DataLoader

EXPERIMENTS = Path("research/experiments")
DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
SEED = 42
EPOCHS = 15
BATCH_SIZE = 4
BASE_CHANNELS = 32
CONFIG_NAME = "B"

SCL_STRATEGIES = {"strict": SCL_INVALID_STRICT, "loose": SCL_INVALID_LOOSE}


def evaluate(model: AttentionUNet, stats, chip_ids: list[str], invalid_codes) -> dict:
    model.eval()
    preds, trues, valids = [], [], []
    with torch.no_grad():
        for chip_id in chip_ids:
            chip = load_chip(chip_id)
            stack = normalize(cached_bs_stack(chip_id, stats.names), stats)
            x = torch.from_numpy(stack.transpose(2, 0, 1)).float().unsqueeze(0).to(DEVICE)
            logits = model(x)
            pred = logits.argmax(dim=1).squeeze(0).cpu().numpy()
            valid = valid_mask(chip, invalid_codes)
            preds.append(pred)
            trues.append(chip.mask.astype(np.int64))
            valids.append(valid)
    return evaluate_predictions(preds, trues, valids)


def make_criterion(loss_name: str, weights: torch.Tensor):
    if loss_name == "combined":
        return CombinedLoss(class_weights=weights, num_classes=4)
    if loss_name == "hierarchical":
        return BurnSeverityLoss(class_weights=weights[1:])
    raise ValueError(f"unknown BS loss: {loss_name}")


def train(
    config_name: str = CONFIG_NAME,
    epochs: int = EPOCHS,
    scl_strategy: str = "strict",
    tag: str = "",
    loss_name: str = "combined",
) -> dict:
    torch.manual_seed(SEED)
    invalid_codes = SCL_STRATEGIES[scl_strategy]
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    train_ids, val_ids = list(train_ids), list(val_ids)
    names = BS_CONFIGS[config_name]

    stats = compute_channel_stats(train_ids, names, invalid_codes)
    weights = class_weights(train_ids, invalid_codes=invalid_codes).to(DEVICE)

    train_ds = BSChipDataset(train_ids, stats, augment=True, invalid_codes=invalid_codes)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)

    model = AttentionUNet(in_channels=len(names), base=BASE_CHANNELS).to(DEVICE)
    optimizer = torch.optim.SGD(
        model.parameters(), lr=1e-3, momentum=0.9, weight_decay=1e-4, nesterov=True
    )
    criterion = make_criterion(loss_name, weights)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    started = time.perf_counter()
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
        print(f"epoch {epoch + 1}/{epochs} loss={epoch_loss / len(train_loader):.4f}", flush=True)

    train_seconds = time.perf_counter() - started
    metrics_own_mask = evaluate(model, stats, val_ids, invalid_codes)
    metrics_strict_mask = evaluate(model, stats, val_ids, SCL_INVALID_STRICT)
    metrics = {
        **metrics_own_mask,
        "metrics_under_strict_mask": metrics_strict_mask,
        "loss": loss_name,
        "scl_strategy": scl_strategy,
        "config": config_name,
        "channel_names": list(names),
        "params": count_parameters(model),
        "train_seconds": round(train_seconds, 1),
        "train_chips": len(train_ids),
        "val_chips": len(val_ids),
        "epochs": epochs,
    }
    print(json.dumps(metrics, indent=2), flush=True)

    suffix = f"_{tag}" if tag else ""
    torch.save(
        {
            "state_dict": model.state_dict(),
            "channel_names": names,
            "base_channels": BASE_CHANNELS,
            "normalization_mean": stats.mean,
            "normalization_std": stats.std,
            "scl_strategy": scl_strategy,
        },
        EXPERIMENTS / f"bs_baseline_model{suffix}.pt",
    )
    (EXPERIMENTS / f"bs_baseline_results{suffix}.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scl-strategy", choices=("strict", "loose"), default="strict")
    parser.add_argument("--loss", choices=("combined", "hierarchical"), default="combined")
    parser.add_argument("--tag", default="")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    args = parser.parse_args()
    train(scl_strategy=args.scl_strategy, tag=args.tag, epochs=args.epochs, loss_name=args.loss)


if __name__ == "__main__":
    main()
