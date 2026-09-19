import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AF_ROOT = REPO_ROOT / "data" / "Мониторинг DATA" / "train" / "af"
AF_ROOT = os.environ.get("KROMA_AF_ROOT", str(DEFAULT_AF_ROOT))

VIIRS_BANDS = ("I1", "I2", "I3", "I4", "I5", "solar_zenith", "sensor_zenith", "valid")
AUX_BANDS = ("landcover", "dem", "t2m", "rh2m", "wind_speed")
MASK_NODATA = 255


@dataclass(frozen=True)
class Chip:
    chip_id: str
    viirs: np.ndarray
    aux: np.ndarray
    mask: np.ndarray | None

    def band(self, name: str) -> np.ndarray:
        if name in VIIRS_BANDS:
            return self.viirs[..., VIIRS_BANDS.index(name)]
        return self.aux[..., AUX_BANDS.index(name)]


def load_meta(root: str = AF_ROOT) -> pd.DataFrame:
    return pd.read_csv(os.path.join(root, "meta.csv"))


def load_chip(chip_id: str, root: str = AF_ROOT, with_mask: bool = True) -> Chip:
    viirs = tifffile.imread(os.path.join(root, "viirs", f"{chip_id}_VIIRS_I1-I5.tif"))
    aux = tifffile.imread(os.path.join(root, "aux", f"{chip_id}_AUX.tif"))
    mask = None
    if with_mask:
        mask_path = os.path.join(root, "masks", f"{chip_id}_MASK.tif")
        if os.path.exists(mask_path):
            mask = tifffile.imread(mask_path)
    return Chip(
        chip_id=chip_id, viirs=viirs.astype(np.float32), aux=aux.astype(np.float32), mask=mask
    )


def valid_mask(chip: Chip) -> np.ndarray:
    valid = chip.band("valid")
    finite = np.isfinite(chip.band("I4")) & np.isfinite(chip.band("I5"))
    result = finite & (valid > 0.5)
    if chip.mask is not None:
        result &= chip.mask != MASK_NODATA
    return result


def fire_mask(chip: Chip) -> np.ndarray | None:
    if chip.mask is None:
        return None
    return (chip.mask == 1).astype(np.uint8)


@lru_cache(maxsize=1)
def tile_key_map(root: str = AF_ROOT) -> pd.Series:
    meta = load_meta(root)
    tile = (
        meta["x_min"].astype(str)
        + "_"
        + meta["y_min"].astype(str)
        + "_"
        + meta["x_max"].astype(str)
        + "_"
        + meta["y_max"].astype(str)
    )
    return pd.Series(tile.values, index=meta["chip_id"].values)
