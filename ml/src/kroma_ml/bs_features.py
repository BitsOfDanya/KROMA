from functools import lru_cache

import numpy as np

from kroma_ml.bs_data import BSChip, load_chip

BAND_GROUPS: dict[str, tuple[str, ...]] = {
    "post_only": ("post_red", "post_nir", "post_swir1", "post_swir2"),
    "pre_post": (
        "pre_red",
        "pre_nir",
        "pre_swir1",
        "pre_swir2",
        "post_red",
        "post_nir",
        "post_swir1",
        "post_swir2",
    ),
    "indices": ("rdnbr",),
    "indices_full": ("dndvi", "dnbr1", "dnbr2", "rdnbr"),
    "sar": ("s1_dvv", "s1_dvh"),
    "terrain": ("dem", "slope", "landcover"),
}

BS_CONFIGS: dict[str, tuple[str, ...]] = {
    "A": BAND_GROUPS["post_only"] + BAND_GROUPS["indices"],
    "B": BAND_GROUPS["pre_post"] + BAND_GROUPS["indices"],
    "C": BAND_GROUPS["pre_post"] + BAND_GROUPS["indices_full"],
    "D": BAND_GROUPS["pre_post"] + BAND_GROUPS["indices_full"] + BAND_GROUPS["sar"],
    "E": (
        BAND_GROUPS["pre_post"]
        + BAND_GROUPS["indices_full"]
        + BAND_GROUPS["sar"]
        + BAND_GROUPS["terrain"]
    ),
}

_S1_CLIP = {"VV": (-25.0, 0.0), "VH": (-32.5, 0.0)}


def _s1_norm(value: np.ndarray, band: str) -> np.ndarray:
    lo, hi = _S1_CLIP[band]
    scaled = np.clip(value / 100.0, lo, hi)
    return (scaled - lo) / (hi - lo)


def bs_channel_stack(chip: BSChip, names: tuple[str, ...]) -> np.ndarray:
    pre_red = chip.s2("pre", "B4") / 10000.0
    pre_nir = chip.s2("pre", "B8A") / 10000.0
    pre_swir1 = chip.s2("pre", "B11") / 10000.0
    pre_swir2 = chip.s2("pre", "B12") / 10000.0
    post_red = chip.s2("post", "B4") / 10000.0
    post_nir = chip.s2("post", "B8A") / 10000.0
    post_swir1 = chip.s2("post", "B11") / 10000.0
    post_swir2 = chip.s2("post", "B12") / 10000.0

    pre_nbr1 = np.clip((pre_nir - pre_swir1) / (pre_nir + pre_swir1 + 1e-8), -1.0, 1.0)
    post_nbr1 = np.clip((post_nir - post_swir1) / (post_nir + post_swir1 + 1e-8), -1.0, 1.0)
    pre_nbr2 = np.clip((pre_nir - pre_swir2) / (pre_nir + pre_swir2 + 1e-8), -1.0, 1.0)
    post_nbr2 = np.clip((post_nir - post_swir2) / (post_nir + post_swir2 + 1e-8), -1.0, 1.0)
    pre_ndvi = np.clip((pre_nir - pre_red) / (pre_nir + pre_red + 1e-8), -1.0, 1.0)
    post_ndvi = np.clip((post_nir - post_red) / (post_nir + post_red + 1e-8), -1.0, 1.0)

    dnbr1 = np.clip(pre_nbr1 - post_nbr1, -2.0, 2.0)
    dnbr2 = np.clip(pre_nbr2 - post_nbr2, -2.0, 2.0)
    dndvi = np.clip(pre_ndvi - post_ndvi, -2.0, 2.0)
    rdnbr = np.clip(dnbr1 / (np.sqrt(np.abs(pre_nbr1)) + 1e-8), -6.0, 6.0) / 6.0

    cache: dict[str, np.ndarray] = {
        "pre_red": pre_red,
        "pre_nir": pre_nir,
        "pre_swir1": pre_swir1,
        "pre_swir2": pre_swir2,
        "post_red": post_red,
        "post_nir": post_nir,
        "post_swir1": post_swir1,
        "post_swir2": post_swir2,
        "dnbr1": dnbr1,
        "dnbr2": dnbr2,
        "dndvi": dndvi,
        "rdnbr": rdnbr,
    }
    layers = []
    for name in names:
        if name in cache:
            layers.append(cache[name])
            continue
        if name == "s1_dvv":
            value = _s1_norm(chip.s1("post", "VV"), "VV") - _s1_norm(chip.s1("pre", "VV"), "VV")
        elif name == "s1_dvh":
            value = _s1_norm(chip.s1("post", "VH"), "VH") - _s1_norm(chip.s1("pre", "VH"), "VH")
        elif name == "dem":
            value = chip.band("dem") / 1000.0
        elif name == "slope":
            value = np.clip(chip.band("slope"), 0.0, 90.0) / 90.0
        elif name == "landcover":
            value = chip.band("landcover")
        else:
            raise ValueError(f"unknown BS channel: {name}")
        cache[name] = value
        layers.append(value)
    stack = np.stack(layers, axis=-1).astype(np.float32)
    return np.nan_to_num(stack, nan=0.0, posinf=0.0, neginf=0.0)


@lru_cache(maxsize=512)
def cached_bs_stack(chip_id: str, names: tuple[str, ...]) -> np.ndarray:
    chip = load_chip(chip_id, with_mask=False)
    return bs_channel_stack(chip, names)
