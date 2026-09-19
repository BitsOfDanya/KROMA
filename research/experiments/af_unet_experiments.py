import argparse
import hashlib
import json
import time

import numpy as np
import torch
from kroma_ml.af_data import load_chip, load_meta
from kroma_ml.af_features import UNET_CONFIGS
from kroma_ml.af_losses import LOSSES
from kroma_ml.af_metrics import Counts, confusion, precision_recall_f1
from kroma_ml.af_split import train_val_split
from kroma_ml.af_threshold import sweep
from kroma_ml.af_torch_data import (
    AFChipDataset,
    ChannelStats,
    compute_channel_stats,
    load_full_chip_tensor,
)
from kroma_ml.af_unet import ResConvBlock, SmallUNet, count_parameters
from torch.utils.data import DataLoader

DEVICE = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
SEED = 42
EPOCHS = 8
BATCH_SIZE = 8
BASE_CHANNELS = 16


def set_seed(seed: int = SEED) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)


def train_unet(
    train_ids: list[str],
    names: tuple[str, ...],
    loss_name: str,
    stats: ChannelStats,
    epochs: int = EPOCHS,
    residual: bool = False,
    extra_counts: dict[str, int] | None = None,
    init_state: dict | None = None,
    val_ids: list[str] | None = None,
) -> SmallUNet:
    set_seed()
    ds = AFChipDataset(
        train_ids, stats, positive_oversample=3, augment=True, extra_counts=extra_counts
    )
    loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    model = SmallUNet(in_channels=len(names), base=BASE_CHANNELS, residual=residual).to(DEVICE)
    if init_state is not None:
        model.load_state_dict(init_state)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = LOSSES[loss_name]
    best_loss = float("inf")
    best_state = None
    stale_epochs = 0
    for epoch in range(epochs):
        model.train()
        total, n = 0.0, 0
        for x, y, v in loader:
            if x.shape[1] != len(names) or x.shape[-2:] != (256, 256):
                raise ValueError("unexpected U-Net input tensor shape")
            x, y, v = x.to(DEVICE), y.to(DEVICE), v.to(DEVICE)
            opt.zero_grad()
            logits = model(x)
            loss = loss_fn(logits, y, v)
            loss.backward()
            opt.step()
            total += loss.item() * x.size(0)
            n += x.size(0)
        if val_ids is None:
            print(f"    epoch {epoch + 1}/{epochs} train_loss={total / n:.4f}")
            continue
        model.eval()
        val_total = Counts(0, 0, 0, 0)
        val_loss = 0.0
        with torch.no_grad():
            for cid in val_ids:
                x, true, valid = load_full_chip_tensor(cid, stats)
                logits = model(x.to(DEVICE))
                target = torch.from_numpy(true.astype(np.float32))[None, None].to(DEVICE)
                allowed = torch.from_numpy(valid.astype(np.float32))[None, None].to(DEVICE)
                val_loss += loss_fn(logits, target, allowed).item()
                proba = torch.sigmoid(logits)[0, 0].cpu().numpy()
                val_total = val_total + confusion(proba >= 0.5, true, valid)
        val_loss /= len(val_ids)
        precision, recall, f1 = precision_recall_f1(val_total)
        print(
            f"    epoch {epoch + 1}/{epochs} train_loss={total / n:.4f} "
            f"val_loss={val_loss:.4f} val_precision={precision:.4f} "
            f"val_recall={recall:.4f} val_f1={f1:.4f}",
            flush=True,
        )
        if val_loss < best_loss - 1e-5:
            best_loss = val_loss
            best_state = {
                key: value.detach().cpu().clone() for key, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= 3:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def evaluate(model: SmallUNet, stats: ChannelStats, chip_ids: list[str]) -> tuple[list, list, list]:
    model.eval()
    probas, trues, valids = [], [], []
    with torch.no_grad():
        for cid in chip_ids:
            x, true, valid = load_full_chip_tensor(cid, stats)
            logits = model(x.to(DEVICE))
            proba = torch.sigmoid(logits)[0, 0].cpu().numpy()
            probas.append(proba)
            trues.append(true)
            valids.append(valid)
    return probas, trues, valids


def score(probas: list, trues: list, valids: list) -> dict:
    coarse_t, _, _ = sweep(probas, trues, valids)
    step = 0.001 if coarse_t >= 0.9 else 0.005
    grid = np.arange(max(0.005, coarse_t - 0.05), min(0.999, coarse_t + 0.05) + 0.0001, step)
    best_t, _, _ = sweep(probas, trues, valids, grid=grid)
    total = Counts(0, 0, 0, 0)
    for proba, true, valid in zip(probas, trues, valids, strict=True):
        total = total + confusion(proba >= best_t, true, valid)
    p, r, f1 = precision_recall_f1(total)
    return {
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
        "threshold": round(best_t, 3),
    }


def benchmark_speed(
    model: SmallUNet, stats: ChannelStats, chip_ids: list[str], device: torch.device
) -> float:
    model = model.to(device)
    model.eval()
    xs = [load_full_chip_tensor(cid, stats)[0].to(device) for cid in chip_ids[:20]]
    with torch.no_grad():
        for x in xs[:3]:
            model(x)
    t0 = time.time()
    with torch.no_grad():
        for x in xs:
            model(x)
    if device.type == "mps":
        torch.mps.synchronize()
    return (time.time() - t0) / len(xs) * 1000


def run_single(config_name: str, loss_name: str, epochs: int, smoke: bool) -> dict:
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    train_ids, val_ids = list(train_ids), list(val_ids)
    if smoke:
        def sample(ids: list[str], positives: int, negatives: int) -> list[str]:
            positive_ids = [cid for cid in ids if (load_chip(cid).mask == 1).any()]
            negative_ids = [cid for cid in ids if not (load_chip(cid).mask == 1).any()]
            return positive_ids[:positives] + negative_ids[:negatives]

        train_ids = sample(train_ids, 8, 4)
        val_ids = sample(val_ids, 4, 2)
    names = UNET_CONFIGS[config_name]
    stats = compute_channel_stats(train_ids, names)
    print(f"device={DEVICE} config={config_name} loss={loss_name} smoke={smoke}", flush=True)
    started = time.perf_counter()
    model = train_unet(train_ids, names, loss_name, stats, epochs=epochs, val_ids=val_ids)
    train_seconds = time.perf_counter() - started
    probas, trues, valids = evaluate(model, stats, val_ids)
    result = {
        "name": f"unet_{config_name}_{loss_name}_corrected",
        **score(probas, trues, valids),
        "train_s": round(train_seconds, 1),
        "params": count_parameters(model),
        "device": str(DEVICE),
        "epochs_max": epochs,
        "smoke": smoke,
    }
    print(result, flush=True)
    if smoke:
        return result
    prefix = f"research/experiments/af_unet_{config_name}_corrected"
    torch.save(
        {
            "state_dict": model.state_dict(),
            "channel_names": names,
            "threshold": result["threshold"],
            "config": config_name,
            "base_channels": BASE_CHANNELS,
            "residual": False,
            "normalization_mean": stats.mean,
            "normalization_std": stats.std,
        },
        f"{prefix}.pt",
    )
    np.savez(
        f"{prefix}_val_probas.npz",
        val_ids=np.array(val_ids),
        **{f"proba_{i}": p for i, p in enumerate(probas)},
        **{f"true_{i}": t for i, t in enumerate(trues)},
        **{f"valid_{i}": v for i, v in enumerate(valids)},
    )
    with open(f"{prefix}.json", "w") as file:
        json.dump(result, file, indent=2)
    return result


def main() -> None:
    meta = load_meta()
    train_ids, val_ids = train_val_split(meta)
    train_ids, val_ids = list(train_ids), list(val_ids)
    print("device:", DEVICE)
    print("train chips:", len(train_ids), "val chips:", len(val_ids))

    results = []
    trained_models = {}

    for config_name, names in UNET_CONFIGS.items():
        print(f"\n=== UNET-{config_name} channels={names} ===")
        stats = compute_channel_stats(train_ids, names)
        best_for_config = None
        for loss_name in ("bce_dice", "focal", "focal_tversky"):
            t0 = time.time()
            model = train_unet(train_ids, names, loss_name, stats, val_ids=val_ids)
            train_time = time.time() - t0
            probas, trues, valids = evaluate(model, stats, val_ids)
            metrics = score(probas, trues, valids)
            row = {
                "name": f"unet_{config_name}_{loss_name}",
                **metrics,
                "train_s": round(train_time, 1),
                "params": count_parameters(model),
            }
            print(row)
            results.append(row)
            if best_for_config is None or metrics["f1"] > best_for_config[1]["f1"]:
                best_for_config = (model, metrics, stats, names, loss_name, probas, trues, valids)
        trained_models[config_name] = best_for_config

    best_config_name = max(trained_models, key=lambda k: trained_models[k][1]["f1"])
    model, metrics, stats, names, loss_name, probas, trues, valids = trained_models[
        best_config_name
    ]
    print(f"\nbest plain U-Net config: {best_config_name} loss={loss_name} f1={metrics['f1']}")

    print("\n=== HARD NEGATIVE ROUND (in-sample FP oversampling) ===")
    train_probas, train_trues, train_valids = evaluate(model, stats, train_ids)
    extra_counts = {}
    for cid, proba, true, valid in zip(
        train_ids, train_probas, train_trues, train_valids, strict=True
    ):
        fp = (proba >= 0.5) & ~true & valid
        n_fp = int(fp.sum())
        if n_fp > 0:
            extra_counts[cid] = min(5, 1 + n_fp // 20)
    print(f"chips with hard negatives: {len(extra_counts)}")
    t0 = time.time()
    hn_model = train_unet(
        train_ids, names, loss_name, stats, epochs=4, extra_counts=extra_counts,
        init_state=model.state_dict(), val_ids=val_ids
    )
    hn_train_time = time.time() - t0
    hn_probas, hn_trues, hn_valids = evaluate(hn_model, stats, val_ids)
    hn_metrics = score(hn_probas, hn_trues, hn_valids)
    row = {
        "name": f"unet_{best_config_name}_{loss_name}_hardneg",
        **hn_metrics,
        "train_s": round(hn_train_time, 1),
        "params": count_parameters(hn_model),
    }
    print(row)
    results.append(row)

    if hn_metrics["f1"] > metrics["f1"]:
        model, metrics, probas, trues, valids = hn_model, hn_metrics, hn_probas, hn_trues, hn_valids

    print("\n=== RESUNET ===")
    t0 = time.time()
    res_model = train_unet(train_ids, names, loss_name, stats, residual=True, val_ids=val_ids)
    res_time = time.time() - t0
    res_probas, res_trues, res_valids = evaluate(res_model, stats, val_ids)
    res_metrics = score(res_probas, res_trues, res_valids)
    row = {
        "name": f"resunet_{best_config_name}_{loss_name}",
        **res_metrics,
        "train_s": round(res_time, 1),
        "params": count_parameters(res_model),
    }
    print(row)
    results.append(row)

    if res_metrics["f1"] > metrics["f1"]:
        model, metrics, probas, trues, valids = (
            res_model, res_metrics, res_probas, res_trues, res_valids
        )

    print("\n=== SPEED ===")
    cpu_ms = benchmark_speed(model, stats, val_ids, torch.device("cpu"))
    print("cpu ms/chip:", round(cpu_ms, 2))
    speed_row = {"cpu_ms_per_chip": round(cpu_ms, 2)}
    if torch.backends.mps.is_available():
        mps_ms = benchmark_speed(model, stats, val_ids, torch.device("mps"))
        print("mps ms/chip:", round(mps_ms, 2))
        speed_row["mps_ms_per_chip"] = round(mps_ms, 2)
    model.to(DEVICE)

    torch.save(
        {
            "state_dict": model.state_dict(),
            "channel_names": names,
            "threshold": metrics["threshold"],
            "config": best_config_name,
            "base_channels": BASE_CHANNELS,
            "residual": isinstance(model.enc1, ResConvBlock),
            "normalization_mean": stats.mean,
            "normalization_std": stats.std,
            "train_ids_sha256": hashlib.sha256("\n".join(train_ids).encode()).hexdigest(),
            "val_ids_sha256": hashlib.sha256("\n".join(val_ids).encode()).hexdigest(),
        },
        "research/experiments/af_unet_best.pt",
    )

    print("\n=== FINAL BEST UNET ===")
    print(best_config_name, metrics, speed_row)

    with open("research/experiments/af_unet_results.json", "w") as f:
        json.dump(
            {"ablation": results, "best": {"config": best_config_name, **metrics, **speed_row}},
            f,
            indent=2,
        )

    np.savez(
        "research/experiments/af_unet_val_probas.npz",
        val_ids=np.array(val_ids),
        **{f"proba_{i}": p for i, p in enumerate(probas)},
        **{f"true_{i}": t for i, t in enumerate(trues)},
        **{f"valid_{i}": v for i, v in enumerate(valids)},
    )
    print("saved best model, results json, and val probas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", choices=UNET_CONFIGS)
    parser.add_argument("--loss", choices=LOSSES, default="bce_dice")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--legacy-all", action="store_true")
    args = parser.parse_args()
    if args.config:
        run_single(args.config, args.loss, args.epochs, args.smoke)
    elif args.legacy_all:
        main()
    else:
        parser.error("choose --config for one run or --legacy-all for the archived full grid")
