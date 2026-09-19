from functools import lru_cache

import numpy as np
from scipy.ndimage import median_filter, uniform_filter

from kroma_ml.af_data import Chip, load_chip

WINDOWS = (3, 5, 7, 11)

FEATURE_NAMES = (
    "I1",
    "I2",
    "I3",
    "I4",
    "I5",
    "I4_I5",
    "solar_zenith",
    "sensor_zenith",
    "landcover",
    "dem",
    "t2m",
    "rh2m",
    "wind_speed",
    *[f"I4_localmed_{s}" for s in WINDOWS],
    *[f"I4_localstd_{s}" for s in WINDOWS],
    *[f"I4_minus_localmed_{s}" for s in WINDOWS],
    *[f"D_localmed_{s}" for s in WINDOWS],
    *[f"D_localstd_{s}" for s in WINDOWS],
    *[f"D_minus_localmed_{s}" for s in WINDOWS],
    "I3_localmed_7",
    "I3_minus_localmed_7",
)

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "raw": ("I1", "I2", "I3", "I4", "I5"),
    "thermal": (
        "I4_I5",
        *[f"I4_localmed_{s}" for s in WINDOWS],
        *[f"I4_localstd_{s}" for s in WINDOWS],
        *[f"I4_minus_localmed_{s}" for s in WINDOWS],
        *[f"D_localmed_{s}" for s in WINDOWS],
        *[f"D_localstd_{s}" for s in WINDOWS],
        *[f"D_minus_localmed_{s}" for s in WINDOWS],
        "I3_localmed_7",
        "I3_minus_localmed_7",
    ),
    "landcover": ("landcover",),
    "weather": ("dem", "t2m", "rh2m", "wind_speed"),
    "angles": ("solar_zenith", "sensor_zenith"),
}


def feature_indices(*groups: str) -> np.ndarray:
    names: list[str] = []
    for group in groups:
        names.extend(FEATURE_GROUPS[group])
    return np.array([FEATURE_NAMES.index(name) for name in names], dtype=int)


def local_stats(x: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = uniform_filter(x, size=size, mode="reflect")
    sq_mean = uniform_filter(x * x, size=size, mode="reflect")
    std = np.sqrt(np.maximum(sq_mean - mean * mean, 0.0))
    med = median_filter(x, size=size, mode="reflect")
    return mean, std, med


def chip_feature_stack(chip: Chip) -> np.ndarray:
    i1 = np.nan_to_num(chip.band("I1"), nan=0.0, posinf=0.0, neginf=0.0)
    i2 = np.nan_to_num(chip.band("I2"), nan=0.0, posinf=0.0, neginf=0.0)
    i3 = np.nan_to_num(chip.band("I3"), nan=0.0, posinf=0.0, neginf=0.0)
    i4 = np.nan_to_num(chip.band("I4"), nan=0.0, posinf=0.0, neginf=0.0)
    i5 = np.nan_to_num(chip.band("I5"), nan=0.0, posinf=0.0, neginf=0.0)
    diff = i4 - i5
    layers = [
        i1,
        i2,
        i3,
        i4,
        i5,
        diff,
        np.nan_to_num(chip.band("solar_zenith"), nan=0.0),
        np.nan_to_num(chip.band("sensor_zenith"), nan=0.0),
        np.nan_to_num(chip.band("landcover"), nan=-1.0),
        np.nan_to_num(chip.band("dem"), nan=0.0),
        np.nan_to_num(chip.band("t2m"), nan=0.0),
        np.nan_to_num(chip.band("rh2m"), nan=0.0),
        np.nan_to_num(chip.band("wind_speed"), nan=0.0),
    ]
    i4_local = {size: local_stats(i4, size) for size in WINDOWS}
    diff_local = {size: local_stats(diff, size) for size in WINDOWS}
    for size in WINDOWS:
        layers.append(i4_local[size][2])
    for size in WINDOWS:
        layers.append(i4_local[size][1])
    for size in WINDOWS:
        layers.append(i4 - i4_local[size][2])
    for size in WINDOWS:
        layers.append(diff_local[size][2])
    for size in WINDOWS:
        layers.append(diff_local[size][1])
    for size in WINDOWS:
        layers.append(diff - diff_local[size][2])
    _, _, med3 = local_stats(i3, 7)
    layers.append(med3)
    layers.append(i3 - med3)
    stack = np.stack(layers, axis=-1).astype(np.float32)
    return np.nan_to_num(stack, nan=0.0, posinf=0.0, neginf=0.0)


@lru_cache(maxsize=512)
def cached_feature_stack(chip_id: str) -> np.ndarray:
    chip = load_chip(chip_id, with_mask=False)
    return chip_feature_stack(chip)


UNET_CHANNEL_GROUPS: dict[str, tuple[str, ...]] = {
    "raw": ("I1", "I2", "I3", "I4", "I5"),
    "thermal": ("I4_I5",),
    "context": ("I4_minus_localmed_7", "D_minus_localmed_7"),
    "aux": (
        "landcover",
        "dem",
        "t2m",
        "rh2m",
        "wind_speed",
        "solar_zenith",
        "sensor_zenith",
        "valid",
    ),
}

UNET_CONFIGS: dict[str, tuple[str, ...]] = {
    "A": UNET_CHANNEL_GROUPS["raw"],
    "B": UNET_CHANNEL_GROUPS["raw"] + UNET_CHANNEL_GROUPS["thermal"],
    "C": (
        UNET_CHANNEL_GROUPS["raw"]
        + UNET_CHANNEL_GROUPS["thermal"]
        + UNET_CHANNEL_GROUPS["context"]
    ),
    "D": (
        UNET_CHANNEL_GROUPS["raw"]
        + UNET_CHANNEL_GROUPS["thermal"]
        + UNET_CHANNEL_GROUPS["context"]
        + UNET_CHANNEL_GROUPS["aux"]
    ),
}


@lru_cache(maxsize=2048)
def cached_unet_stack(chip_id: str, names: tuple[str, ...]) -> np.ndarray:
    chip = load_chip(chip_id, with_mask=False)
    return unet_channel_stack(chip, names)


def unet_channel_stack(chip: Chip, names: tuple[str, ...]) -> np.ndarray:
    i4 = np.nan_to_num(chip.band("I4"), nan=0.0, posinf=0.0, neginf=0.0)
    i5 = np.nan_to_num(chip.band("I5"), nan=0.0, posinf=0.0, neginf=0.0)
    diff = i4 - i5
    cache: dict[str, np.ndarray] = {"I4": i4, "I5": i5, "I4_I5": diff}
    layers = []
    for name in names:
        if name in cache:
            layers.append(cache[name])
            continue
        if name == "I4_minus_localmed_7":
            _, _, med = local_stats(i4, 7)
            value = i4 - med
        elif name == "D_minus_localmed_7":
            _, _, med = local_stats(diff, 7)
            value = diff - med
        elif name == "landcover":
            value = np.nan_to_num(chip.band("landcover"), nan=-1.0)
        else:
            value = np.nan_to_num(chip.band(name), nan=0.0, posinf=0.0, neginf=0.0)
        cache[name] = value
        layers.append(value)
    stack = np.stack(layers, axis=-1).astype(np.float32)
    return np.nan_to_num(stack, nan=0.0, posinf=0.0, neginf=0.0)
