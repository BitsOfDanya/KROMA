import json
from pathlib import Path

import numpy as np
import torch
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_data import load_chip, load_meta, valid_mask
from kroma_ml.bs_features import cached_bs_stack
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_model import AttentionUNet
from kroma_ml.bs_torch_data import BSChannelStats, normalize

MODEL_PATH = Path("research/experiments/bs_baseline_model.pt")
OUT_PATH = Path("research/experiments/bs_calibration.json")


def collect_logits(chip_ids: list[str]):
    ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    names = tuple(ckpt["channel_names"])
    stats = BSChannelStats(
        names=names, mean=ckpt["normalization_mean"], std=ckpt["normalization_std"]
    )
    model = AttentionUNet(in_channels=len(names), base=ckpt["base_channels"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    logits_list, trues, valids = [], [], []
    with torch.no_grad():
        for cid in chip_ids:
            chip = load_chip(cid)
            stack = normalize(cached_bs_stack(cid, names), stats)
            x = torch.from_numpy(stack.transpose(2, 0, 1)).float().unsqueeze(0)
            logits = model(x).squeeze(0).numpy()
            logits_list.append(logits)
            trues.append(chip.mask.astype(np.int64))
            valids.append(valid_mask(chip))
    return logits_list, trues, valids


def score_with_bias(logits_list, trues, valids, bias: np.ndarray) -> dict:
    preds = [
        (logits + bias[:, None, None]).argmax(axis=0).astype(np.int64) for logits in logits_list
    ]
    return evaluate_predictions(preds, trues, valids)


def calibrate() -> dict:
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    val_ids = list(val_ids)
    logits_list, trues, valids = collect_logits(val_ids)

    baseline = score_with_bias(logits_list, trues, valids, np.zeros(4))

    grid = np.arange(-4.0, 0.05, 0.2)
    best_bias = np.zeros(4)
    best_score = baseline["bs_score"]
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

    calibrated = score_with_bias(logits_list, trues, valids, best_bias)
    result = {
        "baseline": baseline,
        "calibrated": calibrated,
        "bias": best_bias.tolist(),
        "val_chips": len(val_ids),
    }
    OUT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(calibrate(), indent=2))
