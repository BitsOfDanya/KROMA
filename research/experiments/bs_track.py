import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from kroma_ml.bs_crop import CONFIGS, load_raw
from kroma_ml.bs_cv import EVAL_MODES, evaluate_scenes, fold_ids, save_predictions, valid_mask
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_fast_models import build_model
from kroma_ml.bs_sampling import (
    PHYS_NAMES,
    TrackCropDataset,
    attach_hard_pool,
    build_pools,
    crop_class1_share,
    hard_pixels,
    parse_mix,
    track_channels,
    track_stats,
)
from kroma_ml.bs_track_losses import TrackLoss
from torch.utils.data import DataLoader

REPO = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("KROMA_BS_TRACK_DIR", REPO / "data" / "processed" / "bs_track"))
OOF = Path(os.environ.get("KROMA_BS_OOF_DIR", REPO / "data" / "processed" / "bs_oof"))
PHYSICS_JSON = REPO / "research" / "experiments" / "bs_physics_baseline_results.json"
SEED = 42


def device() -> torch.device:
    if os.environ.get("KROMA_DEVICE"):
        return torch.device(os.environ["KROMA_DEVICE"])
    return torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")


def physics_thresholds(fold: int) -> tuple[float, float, float]:
    entry = json.loads(PHYSICS_JSON.read_text())["variants"]["fit_dnbr"]["all_valid_mask"]
    params = entry["params_full_train"] if fold == 0 else entry["params_per_fold"][str(fold)]
    return tuple(params["thresholds"])


def scene_logits(model, stats, raws, thresholds, dev) -> list[np.ndarray]:
    model.eval()
    out = []
    with torch.no_grad():
        for raw in raws:
            x = track_channels(
                raw.refl, raw.landcover, raw.scl_pre, raw.scl_post, stats.names, thresholds
            )
            x = np.nan_to_num((x - stats.mean[:, None, None]) / stats.std[:, None, None])
            logits = model(torch.from_numpy(x).float().unsqueeze(0).to(dev))
            out.append(logits.squeeze(0).float().cpu().numpy())
    return out


def checkpoint_path(run_id: str, fold: int) -> Path:
    return OUT / f"{run_id}_f{fold}.pt"


def load_checkpoint(path: Path, dev: torch.device):
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = build_model(ckpt["model"], len(ckpt["names"]))
    model.load_state_dict(ckpt["state_dict"])
    return model.to(dev), ckpt


def hard_pool(run_id: str, fold: int, train_raws, dev, conf: float) -> dict:
    model, ckpt = load_checkpoint(checkpoint_path(run_id, fold), dev)
    stats = ckpt["stats"]
    thresholds = ckpt["thresholds"]
    if set(ckpt["train_ids"]) != {r.chip_id for r in train_raws}:
        raise ValueError("hard-pool source model was trained on a different split")
    out = {}
    for raw, lg in zip(
        train_raws, scene_logits(model, stats, train_raws, thresholds, dev), strict=True
    ):
        probs = torch.softmax(torch.from_numpy(lg), 0).numpy()
        valid = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
        coords, w = hard_pixels(probs, raw.mask.astype(np.int64), valid, conf)
        if len(coords):
            out[raw.chip_id] = (coords, w)
    return out


def run(args) -> dict:
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    dev = device()
    meta = load_meta()
    if args.fold:
        train_ids, val_ids = fold_ids(meta)[args.fold - 1]
    else:
        train_ids, val_ids = meta["chip_id"].tolist(), []
    if args.smoke:
        train_ids, val_ids = train_ids[:10], val_ids[:4]
    if set(train_ids) & set(val_ids):
        raise RuntimeError("train/val overlap")
    started = time.perf_counter()
    train_raws = [load_raw(c) for c in train_ids]
    val_raws = [load_raw(c) for c in val_ids]
    load_seconds = time.perf_counter() - started

    extra = tuple(x for x in args.extra.split(",") if x)
    if set(extra) - set(PHYS_NAMES):
        raise ValueError(f"unknown extra channels {extra}")
    base = CONFIGS[args.config]
    if args.drop_indices:
        base = tuple(n for n in base if n not in ("dnbr12", "rdnbr12", "rdnbr"))
    names = base + extra
    thresholds = physics_thresholds(args.fold) if extra else None
    stats = track_stats(train_raws, names, thresholds)
    pools = {r.chip_id: build_pools(r, rng) for r in train_raws}
    mix = parse_mix(args.mix)
    hard_stats = None
    if "hard" in mix:
        if not args.hard_from:
            raise ValueError("hard sampling needs --hard-from")
        hard = hard_pool(args.hard_from, args.fold, train_raws, dev, args.hard_conf)
        attach_hard_pool(pools, hard, set(train_ids), rng)
        hard_stats = {"chips": len(hard), "pixels": int(sum(len(c) for c, _ in hard.values()))}

    def dataset(seed: int, length: int) -> TrackCropDataset:
        return TrackCropDataset(
            train_raws,
            stats,
            crop=args.crop,
            mix=mix,
            pools=pools,
            thresholds=thresholds,
            brightness_p=args.brightness,
            scl_ignore=args.scl_ignore,
            seed=seed,
            length=length,
        )

    sampler_stats = crop_class1_share(dataset(SEED + 1, 400), 400)
    ds = dataset(SEED, int(len(train_raws) * args.length_mult))
    loader = DataLoader(ds, batch_size=args.batch, shuffle=True, num_workers=0)
    model = build_model(args.model, len(names)).to(dev)
    if args.opt == "sgd":
        opt = torch.optim.SGD(
            model.parameters(), lr=args.lr, momentum=0.9, weight_decay=1e-4, nesterov=True
        )
    else:
        opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-2)
    weights = torch.tensor([1.0, args.w1, 1.0, 1.0], device=dev) if args.w1 != 1.0 else None
    criterion = TrackLoss(
        args.loss, keep_ratio=args.ohem, class_weights=weights, aux_weight=args.aux_weight
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    started = time.perf_counter()
    for epoch in range(args.epochs):
        model.train()
        total, steps = 0.0, 0
        for x, y in loader:
            x, y = x.to(dev), y.to(dev)
            opt.zero_grad(set_to_none=True)
            loss = criterion(model(x), y)
            if torch.isfinite(loss):
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                opt.step()
                total += loss.item()
                steps += 1
        scheduler.step()
        print(
            f"[{args.id} f{args.fold}] epoch {epoch + 1}/{args.epochs} "
            f"loss={total / max(steps, 1):.4f}",
            flush=True,
        )
    train_seconds = time.perf_counter() - started

    OUT.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "model": args.model,
            "names": names,
            "stats": stats,
            "thresholds": thresholds,
            "train_ids": train_ids,
            "args": vars(args),
        },
        checkpoint_path(args.id, args.fold),
    )
    result = {
        "id": args.id,
        "fold": args.fold,
        "args": vars(args),
        "channels": list(names),
        "physics_thresholds": thresholds,
        "params": int(sum(p.numel() for p in model.parameters())),
        "train_chips": len(train_ids),
        "val_chips": len(val_ids),
        "load_seconds": round(load_seconds, 1),
        "train_seconds": round(train_seconds, 1),
        "sampler": {"mix": mix, **sampler_stats},
        "hard_pool": hard_stats,
    }
    if val_raws:
        logits = scene_logits(model, stats, val_raws, thresholds, dev)
        save_predictions(OOF / f"{args.id}_f{args.fold}.npz", val_ids, np.stack(logits))
        preds = [lg.argmax(0).astype(np.uint8) for lg in logits]
        trues = [r.mask.astype(np.uint8) for r in val_raws]
        for name, mode in EVAL_MODES.items():
            valids = [valid_mask(r.scl_pre, r.scl_post, r.refl, mode) for r in val_raws]
            result[name] = evaluate_scenes(preds, trues, valids)
            m = result[name]
            print(
                f"[{args.id} f{args.fold}] {name} bs={m['bs_score']:.4f} burn={m['iou_burn']:.3f} "
                f"iou={[round(v, 3) for v in m['iou_per_class']]} "
                f"P1={m['precision_per_class'][1]:.3f} R1={m['recall_per_class'][1]:.3f}",
                flush=True,
            )
    (OUT / f"{args.id}_f{args.fold}.json").write_text(
        json.dumps(result, indent=2, default=float) + "\n"
    )
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--fold", type=int, default=1, choices=(0, 1, 2, 3))
    p.add_argument("--config", default="B12_lc5", choices=sorted(CONFIGS))
    p.add_argument("--extra", default="")
    p.add_argument("--drop-indices", action="store_true")
    p.add_argument("--model", default="attunet")
    p.add_argument("--mix", default="random:0.5,class1:0.3,burn:0.2")
    p.add_argument("--hard-from", default="")
    p.add_argument("--hard-conf", type=float, default=0.5)
    p.add_argument("--loss", default="ohem")
    p.add_argument("--ohem", type=float, default=0.4)
    p.add_argument("--aux-weight", type=float, default=0.5)
    p.add_argument("--w1", type=float, default=1.0)
    p.add_argument("--opt", default="sgd", choices=("sgd", "adamw"))
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--crop", type=int, default=256)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--length-mult", type=float, default=2.0)
    p.add_argument("--brightness", type=float, default=0.3)
    p.add_argument("--scl-ignore", default="true", choices=("strict", "true"))
    p.add_argument("--smoke", action="store_true")
    run(p.parse_args())


if __name__ == "__main__":
    main()
