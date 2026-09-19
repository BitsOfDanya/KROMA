import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from kroma_ml.bs_crop import build_channels, load_raw
from kroma_ml.bs_model import AttentionUNet, DualHeadAttentionUNet, dual_to_class_logits
from kroma_ml.submission import multiclass_to_binary_rles

DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
ARTIFACTS = Path("artifacts")


def load_member(path: str):
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    names = tuple(ckpt["channel_names"])
    net = DualHeadAttentionUNet if ckpt.get("dual") else AttentionUNet
    model = net(in_channels=len(names), base=ckpt["base_channels"])
    model.load_state_dict(ckpt["state_dict"])
    return model.to(DEVICE).eval(), ckpt


def member_logits(model, ckpt, raw) -> np.ndarray:
    names = tuple(ckpt["channel_names"])
    x = build_channels(raw.refl, raw.landcover, raw.scl_pre, raw.scl_post, names)
    x = (x - ckpt["normalization_mean"][:, None, None]) / ckpt["normalization_std"][:, None, None]
    with torch.no_grad():
        out = model(torch.from_numpy(x).float().unsqueeze(0).to(DEVICE))
        if ckpt.get("dual"):
            out = dual_to_class_logits(out)
    return out.squeeze(0).cpu().numpy()


def predict(members, raw, bias: np.ndarray) -> np.ndarray:
    logits = sum(member_logits(m, c, raw) for m, c in members) / len(members)
    return (logits + bias[:, None, None]).argmax(0).astype(np.uint8)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", required=True)
    p.add_argument("--bias", required=True, help="comma-separated class biases")
    p.add_argument("--tag", required=True)
    args = p.parse_args()
    bias = np.array([float(x) for x in args.bias.split(",")], dtype=np.float32)
    members = [load_member(m) for m in args.models]
    meta = pd.read_csv("data/test/meta.csv")
    ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()

    rows, stats, digests = [], [], []
    started = time.perf_counter()
    for cid in ids:
        raw = load_raw(cid, root="data/test/bs", with_mask=False)
        t0 = time.perf_counter()
        pred = predict(members, raw, bias)
        second = predict(members, raw, bias)
        if not np.array_equal(pred, second):
            raise ValueError(f"non-deterministic inference for {cid}")
        ms = (time.perf_counter() - t0) * 500
        rles = multiclass_to_binary_rles(pred, (1, 2, 3))
        rows += [(cid, k, rles[k]) for k in (1, 2, 3)]
        digests.append(hashlib.sha256(pred.tobytes()).hexdigest())
        stats.append(
            {"chip_id": cid, "ms": ms, **{f"sev{k}_px": int((pred == k).sum()) for k in (1, 2, 3)}}
        )
    frame = pd.DataFrame(rows, columns=["chip_id", "class_id", "rle"])
    out = ARTIFACTS / f"bs_submission_{args.tag}.csv"
    frame.to_csv(out, index=False)
    chips = pd.DataFrame(stats)
    chips.to_csv(ARTIFACTS / f"bs_test_chips_{args.tag}.csv", index=False)
    total = chips[["sev1_px", "sev2_px", "sev3_px"]].sum()
    manifest = {
        "models": args.models,
        "model_sha256": [hashlib.sha256(Path(m).read_bytes()).hexdigest() for m in args.models],
        "class_bias": bias.tolist(),
        "device": str(DEVICE),
        "bs_chips": len(ids),
        "total_seconds": round(time.perf_counter() - started, 1),
        "mean_ms_per_chip": round(float(chips.ms.mean()), 1),
        "mean_burn_fraction": float(total.sum() / (len(ids) * 512 * 512)),
        "total_sev_px": {k: int(v) for k, v in total.items()},
        "deterministic_sha256": hashlib.sha256("".join(digests).encode()).hexdigest(),
        "submission": str(out),
    }
    (ARTIFACTS / f"bs_test_manifest_{args.tag}.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
