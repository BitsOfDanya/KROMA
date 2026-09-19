import json

import numpy as np
import torch
from bs_train import DEVICE, calibrate, evaluators, raw_chips, score
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_features import cached_bs_stack
from kroma_ml.bs_model import AttentionUNet
from kroma_ml.bs_torch_data import BSChannelStats, normalize

ckpt = torch.load(
    "research/experiments/bs_baseline_model.pt", map_location="cpu", weights_only=False
)
names = tuple(ckpt["channel_names"])
stats = BSChannelStats(names, ckpt["normalization_mean"], ckpt["normalization_std"])
model = AttentionUNet(len(names), base=ckpt["base_channels"])
model.load_state_dict(ckpt["state_dict"])
model.to(DEVICE).eval()
_, val_ids = train_val_split(load_meta())
raws = list(raw_chips(list(val_ids)).values())
logits = []
with torch.no_grad():
    for cid in val_ids:
        x = torch.from_numpy(normalize(cached_bs_stack(cid, names), stats).transpose(2, 0, 1))
        logits.append(model(x.float().unsqueeze(0).to(DEVICE)).squeeze(0).cpu().numpy())
trues = [r.mask.astype(np.int64) for r in raws]
out = {}
fixed = np.array([0.0, -1.6, -1.8, -1.6])
for name, valids in evaluators(raws).items():
    out[name] = {
        "v002_fixed_bias": score(logits, trues, valids, fixed),
        "recalibrated": score(logits, trues, valids, calibrate(logits, trues, valids)),
    }
    print(
        name,
        "v002 bias",
        round(out[name]["v002_fixed_bias"]["bs_score"], 4),
        "recal",
        round(out[name]["recalibrated"]["bs_score"], 4),
    )
json.dump(out, open("research/experiments/bs_eval_v002_model.json", "w"), indent=2)
