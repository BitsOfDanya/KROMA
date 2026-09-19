import argparse
from pathlib import Path

import numpy as np
import torch

from kroma_ml.artifacts import resolve
from kroma_ml.bs_crop import build_channels, load_raw
from kroma_ml.bs_model import AttentionUNet, DualHeadAttentionUNet, dual_to_class_logits
from kroma_ml.bs_v004 import V003_BIAS


def pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


DEVICE = pick_device()


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
    with torch.inference_mode():
        out = model(torch.from_numpy(x).float().unsqueeze(0).to(DEVICE))
        if ckpt.get("dual"):
            out = dual_to_class_logits(out)
    return out.squeeze(0).cpu().numpy()


def load_members() -> list:
    return [load_member(str(resolve(key))) for key in ("bs_neural_ndvi", "bs_neural_dual")]


def ensemble_logits(members: list, raw) -> np.ndarray:
    logits = sum(member_logits(m, c, raw) for m, c in members) / len(members)
    return (logits + V003_BIAS[:, None, None]).astype(np.float32)


def v003_logits(chip_ids: list[str], root: str, with_mask: bool) -> dict[str, np.ndarray]:
    members = load_members()
    return {
        cid: ensemble_logits(members, load_raw(cid, root=root, with_mask=with_mask))
        for cid in chip_ids
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--out-dir", required=True, type=Path)
    p.add_argument("--with-mask", action="store_true")
    p.add_argument("chip_ids", nargs="+")
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for cid, logits in v003_logits(args.chip_ids, args.root, args.with_mask).items():
        np.save(args.out_dir / f"{cid}.npy", logits)


if __name__ == "__main__":
    main()
