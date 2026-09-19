import argparse
import json
from pathlib import Path

import numpy as np
import torch
from bs_group_cv import coordinate_calibrate, make_criterion
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_data import SCL_INVALID_STRICT, load_chip, load_meta, valid_mask
from kroma_ml.bs_features import BS_CONFIGS, cached_bs_stack
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_model import AttentionUNet
from kroma_ml.bs_torch_data import BSChipDataset, class_weights, compute_channel_stats, normalize
from torch.utils.data import DataLoader

ROOT = Path("research/experiments")
DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
SEED = 42
BATCH_SIZE = 4
BASE_CHANNELS = 32


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


def run_config(config_name: str, epochs: int) -> dict:
    torch.manual_seed(SEED)
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    train_ids, val_ids = list(train_ids), list(val_ids)
    names = BS_CONFIGS[config_name]

    stats = compute_channel_stats(train_ids, names, SCL_INVALID_STRICT)
    weights = class_weights(train_ids, invalid_codes=SCL_INVALID_STRICT).to(DEVICE)
    train_ds = BSChipDataset(train_ids, stats, augment=True, invalid_codes=SCL_INVALID_STRICT)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)

    model = AttentionUNet(in_channels=len(names), base=BASE_CHANNELS).to(DEVICE)
    optimizer = torch.optim.SGD(
        model.parameters(), lr=1e-3, momentum=0.9, weight_decay=1e-4, nesterov=True
    )
    criterion = make_criterion("combined", weights)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    for epoch in range(epochs):
        model.train()
        epoch_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad(set_to_none=True)
            logits = model(x)
            loss = criterion(logits, y)
            if torch.isfinite(loss):
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()
                epoch_loss += loss.item()
        scheduler.step()
        avg_loss = epoch_loss / len(train_loader)
        print(f"  [{config_name}] epoch {epoch + 1}/{epochs} loss={avg_loss:.4f}", flush=True)

    logits_list, trues, valids = collect_logits(model, stats, val_ids)
    raw = evaluate_predictions([logits.argmax(axis=0) for logits in logits_list], trues, valids)
    bias, calibrated = coordinate_calibrate(logits_list, trues, valids)
    return {
        "config": config_name,
        "channel_names": list(names),
        "raw": raw,
        "calibrated": calibrated,
        "bias": bias.tolist(),
        "train_chips": len(train_ids),
        "val_chips": len(val_ids),
        "epochs": epochs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", default=["B", "C", "D", "E"])
    parser.add_argument("--epochs", type=int, default=15)
    args = parser.parse_args()
    results = {}
    for config_name in args.configs:
        print(f"=== config {config_name} ===", flush=True)
        result = run_config(config_name, args.epochs)
        results[config_name] = result
        print(json.dumps(result, indent=2), flush=True)
    (ROOT / "bs_feature_ablation_results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
