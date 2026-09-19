from dataclasses import dataclass, field

import numpy as np
import torch
from scipy import ndimage
from torch.utils.data import Dataset

from kroma_ml.bs_crop import (
    IGNORE_INDEX,
    RawChip,
    Stats,
    build_channels,
    geometric,
    ignore_map,
    is_categorical,
)
from kroma_ml.bs_physics import spectral_indices

SAMPLER_MODES = ("random", "burn", "class1", "b01", "b12", "hard")
PHYS_NAMES = ("phys_score", "phys_sev")
MAX_POOL = 4000
HARD_PRIORITY = {(1, 0): 4.0, (0, 1): 3.0, (1, 2): 2.0, (2, 1): 2.0}


def parse_mix(text: str) -> dict[str, float]:
    mix = {}
    for part in text.split(","):
        name, value = part.split(":")
        if name not in SAMPLER_MODES:
            raise ValueError(f"unknown sampler mode {name}")
        mix[name] = float(value)
    total = sum(mix.values())
    if total <= 0:
        raise ValueError("mix must have positive mass")
    return {k: v / total for k, v in mix.items() if v > 0}


def boundary_mask(mask: np.ndarray, a: int, b: int, radius: int = 2) -> np.ndarray:
    st = ndimage.generate_binary_structure(2, 2)
    near_a = ndimage.binary_dilation(mask == a, st, iterations=radius)
    near_b = ndimage.binary_dilation(mask == b, st, iterations=radius)
    return near_a & near_b


def _coords(binary: np.ndarray, rng: np.random.Generator, cap: int = MAX_POOL) -> np.ndarray:
    ys, xs = np.nonzero(binary)
    coords = np.stack([ys, xs], 1).astype(np.int32)
    if len(coords) > cap:
        coords = coords[rng.choice(len(coords), cap, replace=False)]
    return coords


@dataclass
class ChipPools:
    pools: dict[str, np.ndarray] = field(default_factory=dict)
    weights: dict[str, np.ndarray] = field(default_factory=dict)


def build_pools(raw: RawChip, rng: np.random.Generator, radius: int = 2) -> ChipPools:
    m = raw.mask
    out = ChipPools()
    out.pools["burn"] = _coords(m > 0, rng)
    out.pools["class1"] = _coords(m == 1, rng)
    out.pools["b01"] = _coords(boundary_mask(m, 0, 1, radius), rng)
    out.pools["b12"] = _coords(boundary_mask(m, 1, 2, radius), rng)
    return out


def hard_pixels(
    probs: np.ndarray, mask: np.ndarray, valid: np.ndarray, conf: float = 0.5
) -> tuple[np.ndarray, np.ndarray]:
    pred = probs.argmax(0)
    top = probs.max(0)
    weights = np.zeros(mask.shape, dtype=np.float32)
    for (t, p), w in HARD_PRIORITY.items():
        weights[(mask == t) & (pred == p) & (top >= conf) & valid] = w
    ys, xs = np.nonzero(weights)
    return np.stack([ys, xs], 1).astype(np.int32), weights[ys, xs]


def attach_hard_pool(
    pools: dict[str, ChipPools],
    hard: dict[str, tuple[np.ndarray, np.ndarray]],
    train_ids: set[str],
    rng: np.random.Generator,
) -> None:
    leaked = set(hard) - set(train_ids)
    if leaked:
        raise ValueError(f"hard pool contains non-train chips: {sorted(leaked)[:5]}")
    for chip_id, (coords, w) in hard.items():
        if len(coords) > MAX_POOL:
            keep = rng.choice(len(coords), MAX_POOL, replace=False, p=w / w.sum())
            coords, w = coords[keep], w[keep]
        pools[chip_id].pools["hard"] = coords
        pools[chip_id].weights["hard"] = w


def crop_origin(
    shape: tuple[int, int],
    pool: np.ndarray | None,
    size: int,
    rng: np.random.Generator,
    weights: np.ndarray | None = None,
) -> tuple[int, int]:
    h, w = shape
    if pool is None or len(pool) == 0:
        return int(rng.integers(0, h - size + 1)), int(rng.integers(0, w - size + 1))
    p = None if weights is None else weights / weights.sum()
    y, x = pool[int(rng.choice(len(pool), p=p))]
    oy = int(np.clip(y - rng.integers(0, size), 0, h - size))
    ox = int(np.clip(x - rng.integers(0, size), 0, w - size))
    return oy, ox


def physics_channels(
    refl: np.ndarray, names: tuple[str, ...], thresholds: tuple[float, float, float] | None
) -> list[np.ndarray]:
    if not names:
        return []
    if thresholds is None:
        raise ValueError("physics channels need train-fold thresholds")
    dnbr = spectral_indices(refl)["dnbr"]
    t1, _, t3 = thresholds
    out = []
    for name in names:
        if name == "phys_score":
            out.append(np.clip((dnbr - t1) / max(t3 - t1, 1e-3), -1.0, 2.0).astype(np.float32))
        elif name == "phys_sev":
            out.append((np.digitize(dnbr, thresholds) / 3.0).astype(np.float32))
        else:
            raise ValueError(name)
    return out


def split_names(names: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    base = tuple(n for n in names if n not in PHYS_NAMES)
    phys = tuple(n for n in names if n in PHYS_NAMES)
    return base, phys


def track_channels(
    refl: np.ndarray,
    landcover: np.ndarray,
    scl_pre: np.ndarray,
    scl_post: np.ndarray,
    names: tuple[str, ...],
    thresholds: tuple[float, float, float] | None = None,
) -> np.ndarray:
    base, phys = split_names(names)
    layers = [build_channels(refl, landcover, scl_pre, scl_post, base)] if base else []
    extra = physics_channels(refl, phys, thresholds)
    if extra:
        layers.append(np.stack(extra))
    return np.concatenate(layers, 0)


def track_stats(
    raws: list[RawChip], names: tuple[str, ...], thresholds: tuple[float, float, float] | None
) -> Stats:
    n = np.zeros(len(names))
    s = np.zeros(len(names))
    q = np.zeros(len(names))
    for raw in raws:
        stack = track_channels(
            raw.refl, raw.landcover, raw.scl_pre, raw.scl_post, names, thresholds
        )
        valid = ignore_map(raw, "true") != IGNORE_INDEX
        v = stack[:, valid].astype(np.float64)
        n += v.shape[1]
        s += v.sum(1)
        q += (v * v).sum(1)
    mean = s / np.maximum(n, 1)
    std = np.sqrt(np.maximum(q / np.maximum(n, 1) - mean**2, 1e-8))
    for i, name in enumerate(names):
        if is_categorical(name):
            mean[i], std[i] = 0.0, 1.0
    return Stats(names, mean.astype(np.float32), std.astype(np.float32))


def crop_class1_share(dataset: "TrackCropDataset", n: int) -> dict:
    shares = []
    for i in range(n):
        _, target = dataset.sample(i)
        valid = target != IGNORE_INDEX
        shares.append(float((target[valid] == 1).mean()) if valid.any() else 0.0)
    a = np.asarray(shares)
    return {
        "crops": n,
        "any_class1": float((a > 0).mean()),
        "class1_ge_1pct": float((a >= 0.01).mean()),
        "class1_ge_5pct": float((a >= 0.05).mean()),
        "mean_class1_share": float(a.mean()),
    }


class TrackCropDataset(Dataset):
    def __init__(
        self,
        raws: list[RawChip],
        stats: Stats,
        crop: int,
        mix: dict[str, float],
        pools: dict[str, ChipPools],
        thresholds: tuple[float, float, float] | None = None,
        brightness_p: float = 0.0,
        scl_ignore: str = "true",
        seed: int = 0,
        length: int | None = None,
    ) -> None:
        self.raws, self.stats, self.crop = raws, stats, crop
        self.modes, self.probs = list(mix), np.asarray(list(mix.values()))
        self.pools, self.thresholds = pools, thresholds
        self.brightness_p, self.scl_ignore = brightness_p, scl_ignore
        self.rng = np.random.default_rng(seed)
        self.length = length or len(raws)
        self.targets = [ignore_map(r, scl_ignore) for r in raws]

    def __len__(self) -> int:
        return self.length

    def sample(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        i = idx % len(self.raws)
        raw, target = self.raws[i], self.targets[i]
        mode = self.modes[int(self.rng.choice(len(self.modes), p=self.probs))]
        cp = self.pools[raw.chip_id]
        pool = None if mode == "random" else cp.pools.get(mode)
        oy, ox = crop_origin(raw.mask.shape, pool, self.crop, self.rng, cp.weights.get(mode))
        sl = (slice(oy, oy + self.crop), slice(ox, ox + self.crop))
        arrays = [
            raw.refl[(slice(None), *sl)],
            raw.landcover[sl],
            raw.scl_pre[sl],
            raw.scl_post[sl],
            target[sl],
        ]
        k, flip = int(self.rng.integers(0, 4)), bool(self.rng.integers(0, 2))
        refl, lc, sp, sq, tgt = geometric(arrays, k, flip)
        if self.brightness_p and self.rng.random() < self.brightness_p:
            refl = refl * np.float32(self.rng.uniform(0.95, 1.05))
        x = track_channels(refl, lc, sp, sq, self.stats.names, self.thresholds)
        return x, tgt

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        x, target = self.sample(idx)
        x = (x - self.stats.mean[:, None, None]) / self.stats.std[:, None, None]
        return torch.from_numpy(np.nan_to_num(x)).float(), torch.from_numpy(target).long()
