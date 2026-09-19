import json
from pathlib import Path

import numpy as np
import torch
from bs_group_cv import coordinate_calibrate
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_data import SCL_INVALID_STRICT, load_chip, load_meta, valid_mask
from kroma_ml.bs_features import cached_bs_stack
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_model import AttentionUNet
from kroma_ml.bs_torch_data import BSChannelStats, normalize

MODEL_PATH = "research/experiments/bs_baseline_model.pt"
DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")


def dihedral(x: torch.Tensor, k: int, flip: bool) -> torch.Tensor:
    x = torch.rot90(x, k, dims=(2, 3))
    return torch.flip(x, dims=(3,)) if flip else x


def inverse_dihedral(x: torch.Tensor, k: int, flip: bool) -> torch.Tensor:
    if flip:
        x = torch.flip(x, dims=(3,))
    return torch.rot90(x, -k, dims=(2, 3))


def predict_log_probs(model, x: torch.Tensor, transforms) -> np.ndarray:
    acc = None
    with torch.no_grad():
        for k, flip in transforms:
            logits = model(dihedral(x, k, flip))
            probs = torch.softmax(inverse_dihedral(logits, k, flip), dim=1)
            acc = probs if acc is None else acc + probs
    return torch.log(acc / len(transforms) + 1e-8).squeeze(0).cpu().numpy()


def main() -> None:
    ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    names = tuple(ckpt["channel_names"])
    stats = BSChannelStats(
        names=names, mean=ckpt["normalization_mean"], std=ckpt["normalization_std"]
    )
    model = AttentionUNet(in_channels=len(names), base=ckpt["base_channels"])
    model.load_state_dict(ckpt["state_dict"])
    model.to(DEVICE).eval()

    _, val_ids = train_val_split(load_meta())
    variants = {
        "none": [(0, False)],
        "flips2": [(0, False), (0, True)],
        "dihedral8": [(k, f) for k in range(4) for f in (False, True)],
    }
    results = {}
    for name, transforms in variants.items():
        logits_list, trues, valids = [], [], []
        for cid in val_ids:
            chip = load_chip(cid)
            stack = normalize(cached_bs_stack(cid, names), stats)
            x = torch.from_numpy(stack.transpose(2, 0, 1)).float().unsqueeze(0).to(DEVICE)
            logits_list.append(predict_log_probs(model, x, transforms))
            trues.append(chip.mask.astype(np.int64))
            valids.append(valid_mask(chip, SCL_INVALID_STRICT))
        raw = evaluate_predictions([lg.argmax(axis=0) for lg in logits_list], trues, valids)
        bias, calibrated = coordinate_calibrate(logits_list, trues, valids)
        results[name] = {"raw": raw, "calibrated": calibrated, "bias": bias.tolist()}
        print(name, round(raw["bs_score"], 4), round(calibrated["bs_score"], 4), flush=True)
    out_path = Path("research/experiments/bs_tta_results.json")
    out_path.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
