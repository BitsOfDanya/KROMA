import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BS_ROOT = REPO_ROOT / "data" / "Мониторинг DATA" / "train" / "bs"
BS_ROOT = os.environ.get("KROMA_BS_ROOT", str(DEFAULT_BS_ROOT))

S2_BANDS = ("B2", "B3", "B4", "B5", "B6", "B7", "B8A", "B11", "B12", "SCL")
S1_BANDS = ("VV", "VH")
AUX_BANDS = ("dem", "slope", "landcover")
S2_SCALE = 10000.0
S1_SCALE = 100.0
SCL_INVALID_STRICT = frozenset({0, 1, 3, 6, 8, 9, 10})
SCL_INVALID_LOOSE = frozenset({0, 1})
SCL_INVALID = SCL_INVALID_STRICT
MASK_CLASSES = (0, 1, 2, 3)
IGNORE_INDEX = 255


@dataclass(frozen=True)
class BSChip:
    chip_id: str
    s2_pre: np.ndarray
    s2_post: np.ndarray
    s1_pre: np.ndarray
    s1_post: np.ndarray
    aux: np.ndarray
    mask: np.ndarray | None

    def s2(self, when: str, name: str) -> np.ndarray:
        array = self.s2_pre if when == "pre" else self.s2_post
        return array[..., S2_BANDS.index(name)]

    def s1(self, when: str, name: str) -> np.ndarray:
        array = self.s1_pre if when == "pre" else self.s1_post
        return array[..., S1_BANDS.index(name)]

    def band(self, name: str) -> np.ndarray:
        return self.aux[..., AUX_BANDS.index(name)]


def load_meta(root: str = BS_ROOT) -> pd.DataFrame:
    return pd.read_csv(os.path.join(root, "meta.csv"))


def load_chip(chip_id: str, root: str = BS_ROOT, with_mask: bool = True) -> BSChip:
    s2_pre = tifffile.imread(os.path.join(root, "sentinel2_pre", f"{chip_id}_Sentinel-2_pre.tif"))
    s2_post = tifffile.imread(
        os.path.join(root, "sentinel2_post", f"{chip_id}_Sentinel-2_post.tif")
    )
    s1_pre = tifffile.imread(os.path.join(root, "sentinel1_pre", f"{chip_id}_Sentinel-1_pre.tif"))
    s1_post = tifffile.imread(
        os.path.join(root, "sentinel1_post", f"{chip_id}_Sentinel-1_post.tif")
    )
    aux = tifffile.imread(os.path.join(root, "aux", f"{chip_id}_AUX.tif"))
    mask = None
    if with_mask:
        mask_path = os.path.join(root, "masks", f"{chip_id}_MASK.tif")
        if os.path.exists(mask_path):
            mask = tifffile.imread(mask_path)
    return BSChip(
        chip_id=chip_id,
        s2_pre=s2_pre.astype(np.float32),
        s2_post=s2_post.astype(np.float32),
        s1_pre=s1_pre.astype(np.float32),
        s1_post=s1_post.astype(np.float32),
        aux=aux.astype(np.float32),
        mask=mask,
    )


def valid_mask(chip: BSChip, invalid_codes: frozenset[int] = SCL_INVALID) -> np.ndarray:
    scl_pre = chip.s2("pre", "SCL")
    scl_post = chip.s2("post", "SCL")
    invalid_pre = np.isin(scl_pre, list(invalid_codes))
    invalid_post = np.isin(scl_post, list(invalid_codes))
    return ~(invalid_pre | invalid_post)
