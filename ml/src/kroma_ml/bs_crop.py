from dataclasses import dataclass

import numpy as np
import torch
from torch.utils.data import Dataset

from kroma_ml.bs_data import BS_ROOT, IGNORE_INDEX, SCL_INVALID_STRICT, load_chip

TRUE_INVALID = frozenset({0, 1})
REFL_NAMES = (
    "pre_red",
    "pre_nir",
    "pre_swir1",
    "pre_swir2",
    "post_red",
    "post_nir",
    "post_swir1",
    "post_swir2",
)
_S2_BANDS = ("B4", "B8A", "B11", "B12")
LC_GROUPS = {
    "lc_forest": (10, 20, 95),
    "lc_grass": (30, 100),
    "lc_crop": (40,),
    "lc_wet": (80, 90),
}
LC_NAMES = (*LC_GROUPS, "lc_other")
Q_NAMES = ("q_cloud", "q_shadow", "q_dark", "q_water", "q_snow", "q_clear")
CATEGORICAL_PREFIXES = ("lc_", "q_")

CONFIGS: dict[str, tuple[str, ...]] = {
    "B": (*REFL_NAMES, "rdnbr"),
    "B12": (*REFL_NAMES, "dnbr12", "rdnbr12"),
    "B12_lc5": (*REFL_NAMES, "dnbr12", "rdnbr12", *LC_NAMES),
    "B12_lc5_ndvi": (*REFL_NAMES, "dnbr12", "rdnbr12", *LC_NAMES, "ndvi_pre", "ndvi_post", "dndvi"),
    "B12_lc5_ndvi_q": (
        *REFL_NAMES,
        "dnbr12",
        "rdnbr12",
        *LC_NAMES,
        "ndvi_pre",
        "ndvi_post",
        "dndvi",
        *Q_NAMES,
    ),
}


@dataclass(frozen=True)
class RawChip:
    chip_id: str
    refl: np.ndarray
    scl_pre: np.ndarray
    scl_post: np.ndarray
    landcover: np.ndarray
    mask: np.ndarray


def load_raw(chip_id: str, root: str = BS_ROOT, with_mask: bool = True) -> RawChip:
    chip = load_chip(chip_id, root=root, with_mask=with_mask)
    bands = []
    for when in ("pre", "post"):
        for band in _S2_BANDS:
            bands.append(chip.s2(when, band) / 10000.0)
    return RawChip(
        chip_id=chip_id,
        refl=np.stack(bands).astype(np.float32),
        scl_pre=chip.s2("pre", "SCL").astype(np.uint8),
        scl_post=chip.s2("post", "SCL").astype(np.uint8),
        landcover=chip.band("landcover").astype(np.int16),
        mask=(chip.mask if chip.mask is not None else np.zeros(chip.s2_pre.shape[:2])).astype(
            np.uint8
        ),
    )


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.clip((a - b) / (a + b + 1e-8), -1.0, 1.0)


def is_categorical(name: str) -> bool:
    return name.startswith(CATEGORICAL_PREFIXES)


def clear_mask(scl_pre: np.ndarray, scl_post: np.ndarray) -> np.ndarray:
    bad = np.isin(scl_pre, list(SCL_INVALID_STRICT)) | np.isin(scl_post, list(SCL_INVALID_STRICT))
    return ~bad


def build_channels(
    refl: np.ndarray,
    landcover: np.ndarray,
    scl_pre: np.ndarray,
    scl_post: np.ndarray,
    names: tuple[str, ...],
) -> np.ndarray:
    pre_red, pre_nir, pre_swir1, pre_swir2, post_red, post_nir, post_swir1, post_swir2 = refl
    cache: dict[str, np.ndarray] = dict(zip(REFL_NAMES, refl, strict=True))
    layers = []
    for name in names:
        if name not in cache:
            if name == "rdnbr":
                dnbr = np.clip(_nd(pre_nir, pre_swir1) - _nd(post_nir, post_swir1), -2.0, 2.0)
                cache[name] = (
                    np.clip(dnbr / (np.sqrt(np.abs(_nd(pre_nir, pre_swir1))) + 1e-2), -6, 6) / 6
                )
            elif name in ("dnbr12", "rdnbr12"):
                pre_nbr, post_nbr = _nd(pre_nir, pre_swir2), _nd(post_nir, post_swir2)
                dnbr = np.clip(pre_nbr - post_nbr, -2.0, 2.0)
                cache["dnbr12"] = dnbr
                cache["rdnbr12"] = np.clip(dnbr / (np.sqrt(np.abs(pre_nbr)) + 1e-2), -6, 6) / 6
            elif name in ("ndvi_pre", "ndvi_post", "dndvi"):
                cache["ndvi_pre"], cache["ndvi_post"] = (
                    _nd(pre_nir, pre_red),
                    _nd(post_nir, post_red),
                )
                cache["dndvi"] = np.clip(cache["ndvi_pre"] - cache["ndvi_post"], -2.0, 2.0)
            elif name in LC_GROUPS:
                cache[name] = np.isin(landcover, LC_GROUPS[name]).astype(np.float32)
            elif name == "lc_other":
                known = [c for codes in LC_GROUPS.values() for c in codes]
                cache[name] = (~np.isin(landcover, known)).astype(np.float32)
            elif name == "q_cloud":
                cache[name] = (np.isin(scl_pre, (8, 9, 10)) | np.isin(scl_post, (8, 9, 10))).astype(
                    np.float32
                )
            elif name == "q_shadow":
                cache[name] = ((scl_pre == 3) | (scl_post == 3)).astype(np.float32)
            elif name == "q_dark":
                cache[name] = ((scl_pre == 2) | (scl_post == 2)).astype(np.float32)
            elif name == "q_water":
                cache[name] = ((scl_pre == 6) | (scl_post == 6)).astype(np.float32)
            elif name == "q_snow":
                cache[name] = ((scl_pre == 11) | (scl_post == 11)).astype(np.float32)
            elif name == "q_clear":
                cache[name] = clear_mask(scl_pre, scl_post).astype(np.float32)
            else:
                raise ValueError(f"unknown BS channel: {name}")
        layers.append(cache[name])
    return np.nan_to_num(np.stack(layers).astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)


def geometric(arrays: list[np.ndarray], k: int, flip: bool) -> list[np.ndarray]:
    out = []
    for a in arrays:
        a = np.rot90(a, k, axes=(-2, -1))
        if flip:
            a = a[..., ::-1]
        out.append(np.ascontiguousarray(a))
    return out


MODES = ("random", "class1", "burn", "hardneg", "boundary01")


def origin_from_point(y: int, x: int, h: int, w: int, size: int, rng: np.random.Generator):

    oy = int(np.clip(y - rng.integers(0, size), 0, h - size))
    ox = int(np.clip(x - rng.integers(0, size), 0, w - size))
    return oy, ox


def boundary01_points(mask: np.ndarray, width: int = 2) -> tuple[np.ndarray, np.ndarray]:
    from scipy.ndimage import binary_dilation

    cls0, cls1 = mask == 0, mask == 1
    near = (cls0 & binary_dilation(cls1, iterations=width)) | (
        cls1 & binary_dilation(cls0, iterations=width)
    )
    return np.nonzero(near)


def mine_points(mask: np.ndarray, logits: np.ndarray, valid: np.ndarray) -> dict:
    e = np.exp(logits.astype(np.float32) - logits.max(0, keepdims=True))
    prob = e / e.sum(0, keepdims=True)
    pred, conf = prob.argmax(0), prob.max(0)
    pools = {
        "hardneg": valid & (mask == 0) & (pred > 0) & (1.0 - prob[0] > 0.5),
        "hardpos": valid & (mask == 1) & (pred != 1) & (conf > 0.6),
    }
    return {k: np.nonzero(v) for k, v in pools.items()}


def choose_crop_origin(
    mask: np.ndarray, mode: str, size: int, rng: np.random.Generator
) -> tuple[int, int]:
    h, w = mask.shape
    if mode == "random":
        return int(rng.integers(0, h - size + 1)), int(rng.integers(0, w - size + 1))
    target = (mask == 1) if mode == "class1" else (mask > 0)
    ys, xs = np.nonzero(target)
    if len(ys) == 0:
        return choose_crop_origin(mask, "random", size, rng)
    i = int(rng.integers(0, len(ys)))
    return origin_from_point(int(ys[i]), int(xs[i]), h, w, size, rng)


@dataclass(frozen=True)
class Stats:
    names: tuple[str, ...]
    mean: np.ndarray
    std: np.ndarray


def compute_stats(raws: list[RawChip], names: tuple[str, ...]) -> Stats:
    n = np.zeros(len(names))
    s = np.zeros(len(names))
    q = np.zeros(len(names))
    for raw in raws:
        stack = build_channels(raw.refl, raw.landcover, raw.scl_pre, raw.scl_post, names)
        valid = ~np.isin(raw.scl_pre, list(TRUE_INVALID)) & ~np.isin(
            raw.scl_post, list(TRUE_INVALID)
        )
        for i, name in enumerate(names):
            if is_categorical(name):
                continue
            v = stack[i][valid].astype(np.float64)
            n[i] += v.size
            s[i] += v.sum()
            q[i] += (v * v).sum()
    mean = s / np.maximum(n, 1)
    std = np.sqrt(np.maximum(q / np.maximum(n, 1) - mean**2, 1e-8))
    for i, name in enumerate(names):
        if is_categorical(name):
            mean[i], std[i] = 0.0, 1.0
    return Stats(names, mean.astype(np.float32), std.astype(np.float32))


def ignore_map(raw: RawChip, scl_ignore: str) -> np.ndarray:
    codes = SCL_INVALID_STRICT if scl_ignore == "strict" else TRUE_INVALID
    bad = np.isin(raw.scl_pre, list(codes)) | np.isin(raw.scl_post, list(codes))
    return np.where(bad, IGNORE_INDEX, raw.mask).astype(np.int64)


class CropDataset(Dataset):
    def __init__(
        self,
        raws: list[RawChip],
        stats: Stats,
        crop: int | None = None,
        mix: tuple[float, float, float] = (0.5, 0.3, 0.2),
        geom_aug: bool = True,
        brightness_p: float = 0.0,
        scl_ignore: str = "strict",
        seed: int = 0,
        length: int | None = None,
        pools: dict | None = None,
        hardpos_frac: float = 0.5,
    ) -> None:
        self.raws, self.stats, self.crop = raws, stats, crop
        self.mix = tuple(mix) + (0.0,) * (len(MODES) - len(mix))
        self.pools, self.hardpos_frac = pools or {}, hardpos_frac
        self.pool_chips = {
            m: [i for i, p in enumerate(self.pools.get(m, [])) if p is not None and len(p[0])]
            for m in ("hardneg", "boundary01", "hardpos")
        }
        self.geom_aug, self.brightness_p, self.scl_ignore = geom_aug, brightness_p, scl_ignore
        self.rng = np.random.default_rng(seed)
        self.length = length or len(raws)
        self.targets = [ignore_map(r, scl_ignore) for r in raws]

    def __len__(self) -> int:
        return self.length

    def sample(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        i = idx % len(self.raws)
        mode = str(self.rng.choice(MODES, p=self.mix)) if self.crop else "random"
        if mode in ("hardneg", "boundary01"):
            if self.pool_chips[mode]:
                i = int(self.rng.choice(self.pool_chips[mode]))
            else:
                mode = "random"
        raw, target = self.raws[i], self.targets[i]
        refl, lc, sp, sq = raw.refl, raw.landcover, raw.scl_pre, raw.scl_post
        if self.crop:
            h, w = raw.mask.shape
            point = None
            if mode in ("hardneg", "boundary01"):
                ys, xs = self.pools[mode][i]
                j = int(self.rng.integers(0, len(ys)))
                point = (int(ys[j]), int(xs[j]))
            elif mode == "class1" and i in self.pool_chips["hardpos"]:
                if self.rng.random() < self.hardpos_frac:
                    ys, xs = self.pools["hardpos"][i]
                    j = int(self.rng.integers(0, len(ys)))
                    point = (int(ys[j]), int(xs[j]))
            if point is not None:
                oy, ox = origin_from_point(*point, h, w, self.crop, self.rng)
            else:
                oy, ox = choose_crop_origin(raw.mask, mode, self.crop, self.rng)
            sl = (slice(oy, oy + self.crop), slice(ox, ox + self.crop))
            refl, lc, sp, sq, target = refl[(slice(None), *sl)], lc[sl], sp[sl], sq[sl], target[sl]
        if self.geom_aug:
            k, flip = int(self.rng.integers(0, 4)), bool(self.rng.integers(0, 2))
            refl, lc, sp, sq, target = geometric([refl, lc, sp, sq, target], k, flip)
        if self.brightness_p and self.rng.random() < self.brightness_p:
            refl = refl * np.float32(self.rng.uniform(0.95, 1.05))
        x = build_channels(refl, lc, sp, sq, self.stats.names)
        return x, target

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        x, target = self.sample(idx)
        x = (x - self.stats.mean[:, None, None]) / self.stats.std[:, None, None]
        assert set(np.unique(target).tolist()) <= {0, 1, 2, 3, IGNORE_INDEX}
        return torch.from_numpy(x).float(), torch.from_numpy(target).long()
