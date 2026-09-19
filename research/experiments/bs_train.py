import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import torch
from kroma_ml.af_split import train_val_split
from kroma_ml.bs_crop import (
    CONFIGS,
    LC_GROUPS,
    CropDataset,
    Stats,
    boundary01_points,
    build_channels,
    compute_stats,
    ignore_map,
    load_raw,
    mine_points,
)
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_losses import CombinedLoss, DualHeadLoss, OHEMLoss
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_model import AttentionUNet, DualHeadAttentionUNet, dual_to_class_logits
from torch.utils.data import DataLoader

ROOT = Path("research/experiments")
RAW_CACHE = Path("/tmp/bs_raw_cache.joblib")
DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
SEED = 42


def raw_chips(ids: list[str]) -> dict:
    cache = joblib.load(RAW_CACHE) if RAW_CACHE.exists() else {}
    missing = [i for i in ids if i not in cache]
    for chip_id in missing:
        cache[chip_id] = load_raw(chip_id)
    if missing:
        joblib.dump(cache, RAW_CACHE)
    return {i: cache[i] for i in ids}


def build_pools(train_ids, raws, oof_run: str, use: tuple[str, ...]):
    logits = {}
    for k in (1, 2, 3):
        d = np.load(f"/tmp/bs_oof/{oof_run}_f{k}.npz")
        logits.update({str(c): lg for c, lg in zip(d["ids"], d["logits"], strict=True)})
    pools = {m: [] for m in use}
    comp = {"hardneg": {}, "hardpos": 0, "boundary01": 0}
    for cid in train_ids:
        raw = raws[cid]
        valid = ignore_map(raw, "true") != 255
        mined = mine_points(raw.mask, logits[cid], valid)
        for m in use:
            pts = boundary01_points(raw.mask) if m == "boundary01" else mined[m]
            pools[m].append(pts if len(pts[0]) else None)
            if m == "hardneg" and len(pts[0]):
                for name, codes in {**LC_GROUPS, "other": ()}.items():
                    known = [c for v in LC_GROUPS.values() for c in v]
                    sel = (
                        np.isin(raw.landcover[pts], codes)
                        if codes
                        else ~np.isin(raw.landcover[pts], known)
                    )
                    comp["hardneg"][name] = comp["hardneg"].get(name, 0) + int(sel.sum())
            elif m != "hardneg":
                comp[m] += int(len(pts[0]))
    return pools, comp


def soft_weights(raws, cap: float = 3.0) -> torch.Tensor:
    counts = np.zeros(4)
    for raw in raws:
        counts += np.bincount(raw.mask.ravel(), minlength=4)
    w = (counts.sum() / np.maximum(counts, 1)) ** 0.5
    return torch.tensor(np.minimum(w / w.mean(), cap), dtype=torch.float32)


def make_loss(args, raws):
    weights = soft_weights(raws).to(DEVICE) if args.weights == "soft" else None
    if args.loss == "ohem":
        return OHEMLoss(args.ohem, class_weights=weights)
    if args.loss == "dual":
        return DualHeadLoss(ordinal_weight=args.ordinal)
    if args.loss == "combined":
        return CombinedLoss(class_weights=weights, num_classes=4)
    raise ValueError(args.loss)


def full_scene_logits(model, stats, raws) -> list[np.ndarray]:
    model.eval()
    out = []
    with torch.no_grad():
        for raw in raws:
            x = build_channels(raw.refl, raw.landcover, raw.scl_pre, raw.scl_post, stats.names)
            x = (x - stats.mean[:, None, None]) / stats.std[:, None, None]
            logits = model(torch.from_numpy(x).float().unsqueeze(0).to(DEVICE))
            if isinstance(model, DualHeadAttentionUNet):
                logits = dual_to_class_logits(logits)
            out.append(logits.squeeze(0).cpu().numpy())
    return out


def evaluators(raws):
    return {
        "strict_mask": [ignore_map(r, "strict") != 255 for r in raws],
        "all_valid_mask": [ignore_map(r, "true") != 255 for r in raws],
    }


def score(logits, trues, valids, bias, step: int = 1) -> dict:
    preds = [
        (lg[:, ::step, ::step] + bias[:, None, None]).argmax(0).astype(np.int64) for lg in logits
    ]
    t = [x[::step, ::step] for x in trues]
    v = [x[::step, ::step] for x in valids]
    return evaluate_predictions(preds, t, v)


def calibrate(logits, trues, valids) -> np.ndarray:
    grid = np.arange(-4.0, 1.01, 0.2)
    bias = np.zeros(4)
    best = score(logits, trues, valids, bias, step=2)["bs_score"]
    for _ in range(3):
        improved = False
        for c in (1, 2, 3):
            for value in grid:
                cand = bias.copy()
                cand[c] = value
                s = score(logits, trues, valids, cand, step=2)["bs_score"]
                if s > best:
                    best, bias, improved = s, cand, True
        if not improved:
            break
    return bias


def confusion_and_extras(logits, trues, valids, bias, landcovers=None) -> dict:
    cm = np.zeros((4, 4), dtype=np.int64)
    lc_fp = {name: [0, 0] for name in ("cropland", "grass", "forest", "wet")}
    lc_codes = {"cropland": (40,), "grass": (30, 100), "forest": (10, 20, 95), "wet": (80, 90)}
    for n, (lg, t, v) in enumerate(zip(logits, trues, valids, strict=True)):
        p = (lg + bias[:, None, None]).argmax(0)
        cm += np.bincount((t[v] * 4 + p[v]).astype(np.int64), minlength=16).reshape(4, 4)
        if landcovers is not None:
            for name, codes in lc_codes.items():
                sel = v & (t == 0) & np.isin(landcovers[n], codes)
                lc_fp[name][0] += int((sel & (p == 1)).sum())
                lc_fp[name][1] += int(sel.sum())
    tp1, fp1, fn1 = cm[1, 1], cm[:, 1].sum() - cm[1, 1], cm[1].sum() - cm[1, 1]
    burn_tp = cm[1:, 1:].sum()
    burn_fp, burn_fn = cm[0, 1:].sum(), cm[1:, 0].sum()
    return {
        "precision_1": float(tp1 / max(tp1 + fp1, 1)),
        "recall_1": float(tp1 / max(tp1 + fn1, 1)),
        "burn_precision": float(burn_tp / max(burn_tp + burn_fp, 1)),
        "burn_recall": float(burn_tp / max(burn_tp + burn_fn, 1)),
        "leak_0to1": float(cm[0, 1] / max(cm[0].sum(), 1)),
        "fp_0to1_px": int(cm[0, 1]),
        "fn_1to0_px": int(cm[1, 0]),
        "conf_1to2_px": int(cm[1, 2]),
        "conf_2to1_px": int(cm[2, 1]),
        "confusion": cm.tolist(),
        "fp_0to1_by_landcover": {
            k: {"px": a, "rate": a / max(b, 1)} for k, (a, b) in lc_fp.items()
        },
    }


def run(args) -> dict:
    torch.manual_seed(SEED)
    meta = load_meta()
    if args.fold:
        from kroma_ml.af_split import group_key
        from sklearn.model_selection import GroupKFold

        ids = meta["chip_id"].to_numpy()
        splits = list(GroupKFold(n_splits=3).split(ids, groups=group_key(meta).to_numpy()))
        tr, va = splits[args.fold - 1]
        train_ids, val_ids = ids[tr].tolist(), ids[va].tolist()
    else:
        train_ids, val_ids = (list(x) for x in train_val_split(meta))
    if args.full:
        train_ids, val_ids = meta["chip_id"].tolist(), []
    if args.smoke:
        train_ids, val_ids = train_ids[:12], val_ids[:6]
    raws = raw_chips(train_ids + val_ids)
    train_raws, val_raws = [raws[i] for i in train_ids], [raws[i] for i in val_ids]
    names = CONFIGS[args.config]
    init = torch.load(args.init, map_location="cpu", weights_only=False) if args.init else None
    if init:
        names = tuple(init["channel_names"])
        stats = Stats(names, init["normalization_mean"], init["normalization_std"])
    else:
        stats = compute_stats(train_raws, names)
    pools, pool_counts = None, None
    if args.pools != "none":
        use = tuple(args.pools.split(","))
        pools, pool_counts = build_pools(train_ids, raws, args.oof_run, use)
        print(f"[{args.id}] pool sizes: {pool_counts}", flush=True)

    ds = CropDataset(
        train_raws,
        stats,
        crop=args.crop or None,
        mix=tuple(float(x) for x in args.mix.split(",")),
        geom_aug=bool(args.geom),
        brightness_p=args.brightness,
        scl_ignore=args.scl_ignore,
        seed=SEED,
        length=int(len(train_raws) * args.length_mult),
        pools=pools,
    )
    batch = args.batch or (8 if args.crop else 4)
    loader = DataLoader(ds, batch_size=batch, shuffle=True, num_workers=0)
    net = DualHeadAttentionUNet if args.loss == "dual" else AttentionUNet
    model = net(in_channels=len(names), base=32).to(DEVICE)
    if init:
        model.load_state_dict(init["state_dict"])
    optimizer = torch.optim.SGD(
        model.parameters(), lr=args.lr, momentum=0.9, weight_decay=1e-4, nesterov=True
    )
    criterion = make_loss(args, train_raws)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    started = time.perf_counter()
    for epoch in range(args.epochs):
        model.train()
        total, steps = 0.0, 0
        optimizer.zero_grad(set_to_none=True)
        for n, (x, y) in enumerate(loader, start=1):
            x, y = x.to(DEVICE), y.to(DEVICE)
            loss = criterion(model(x), y)
            if torch.isfinite(loss):
                (loss / args.accum).backward()
                total += loss.item()
                steps += 1
            if n % args.accum == 0 or n == len(loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
        scheduler.step()
        avg = total / max(steps, 1)
        print(f"[{args.id}] epoch {epoch + 1}/{args.epochs} loss={avg:.4f}", flush=True)
    train_seconds = time.perf_counter() - started

    if args.full:
        torch.save(
            {
                "state_dict": model.state_dict(),
                "channel_names": names,
                "base_channels": 32,
                "normalization_mean": stats.mean,
                "normalization_std": stats.std,
                "dual": args.loss == "dual",
                "args": vars(args),
                "train_chips": len(train_ids),
            },
            ROOT / f"bs_full_{args.id}.pt",
        )
        return {"id": args.id, "train_seconds": round(train_seconds, 1)}
    t_inf = time.perf_counter()
    logits = full_scene_logits(model, stats, val_raws)
    infer_ms = (time.perf_counter() - t_inf) * 1000 / max(len(val_raws), 1)
    trues = [r.mask.astype(np.int64) for r in val_raws]
    result = {
        "id": args.id,
        "args": vars(args),
        "channels": list(names),
        "train_chips": len(train_ids),
        "val_chips": len(val_ids),
        "train_seconds": round(train_seconds, 1),
        "pool_counts": pool_counts,
        "infer_ms_per_chip": round(infer_ms, 1),
    }
    if args.fold:
        oof = Path("/tmp/bs_oof")
        oof.mkdir(exist_ok=True)
        np.savez(
            oof / f"{args.id}_f{args.fold}.npz",
            ids=np.array(val_ids),
            logits=np.stack([lg.astype(np.float16) for lg in logits]),
        )
        for eval_name, valids in evaluators(val_raws).items():
            result[eval_name] = {"raw": score(logits, trues, valids, np.zeros(4))}
            print(
                f"[{args.id}] fold{args.fold} {eval_name} "
                f"raw={result[eval_name]['raw']['bs_score']:.4f}",
                flush=True,
            )
        (ROOT / f"bs_exp_{args.id}_f{args.fold}.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        return result
    biases = {}
    for eval_name, valids in evaluators(val_raws).items():
        raw_metrics = score(logits, trues, valids, np.zeros(4))
        bias = calibrate(logits, trues, valids)
        biases[eval_name] = bias.tolist()
        cal = score(logits, trues, valids, bias)
        result[eval_name] = {
            "raw": raw_metrics,
            "calibrated": cal,
            "bias": bias.tolist(),
            "extras": confusion_and_extras(
                logits, trues, valids, bias, [r.landcover for r in val_raws]
            ),
        }
        ious = [round(v, 3) for v in cal["iou_per_class"]]
        print(
            f"[{args.id}] {eval_name}: raw={raw_metrics['bs_score']:.4f} "
            f"cal={cal['bs_score']:.4f} burn={cal['iou_burn']:.4f} iou={ious}",
            flush=True,
        )
    torch.save(
        {
            "state_dict": model.state_dict(),
            "channel_names": names,
            "base_channels": 32,
            "normalization_mean": stats.mean,
            "normalization_std": stats.std,
            "bias": biases,
            "args": vars(args),
        },
        ROOT / f"bs_exp_{args.id}.pt",
    )
    (ROOT / f"bs_exp_{args.id}.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--config", default="B", choices=sorted(CONFIGS))
    p.add_argument("--crop", type=int, default=0)
    p.add_argument("--mix", default="0.5,0.3,0.2")
    p.add_argument("--geom", type=int, default=1)
    p.add_argument("--brightness", type=float, default=0.0)
    p.add_argument("--scl-ignore", default="strict", choices=("strict", "true"))
    p.add_argument("--loss", default="combined", choices=("combined", "ohem", "dual"))
    p.add_argument("--ohem", type=float, default=0.4)
    p.add_argument("--ordinal", type=float, default=0.0)
    p.add_argument("--weights", default="none", choices=("none", "soft"))
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--length-mult", type=float, default=1.0)
    p.add_argument("--fold", type=int, default=0, choices=(0, 1, 2, 3))
    p.add_argument("--batch", type=int, default=0)
    p.add_argument("--accum", type=int, default=1)
    p.add_argument("--full", action="store_true")
    p.add_argument("--init", default="")
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--pools", default="none", help="comma list of hardneg,hardpos,boundary01")
    p.add_argument("--oof-run", default="cv_ndvi")
    p.add_argument("--smoke", action="store_true")
    run(p.parse_args())


if __name__ == "__main__":
    main()
