from dataclasses import dataclass

import numpy as np

from kroma_ml.af_data import Chip, valid_mask
from kroma_ml.af_features import local_stats


@dataclass(frozen=True)
class PhysicsParams:
    i4_min: float
    diff_min: float
    anom_min: float
    window: int = 7


DEFAULT_PARAMS = PhysicsParams(i4_min=330.0, diff_min=24.0, anom_min=0.0, window=7)


def physics_signals(chip: Chip, window: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    i4 = chip.band("I4")
    i5 = chip.band("I5")
    diff = i4 - i5
    _, _, med4 = local_stats(i4, window)
    anom = i4 - med4
    return i4, diff, anom


def predict(chip: Chip, params: PhysicsParams = DEFAULT_PARAMS) -> np.ndarray:
    i4, diff, anom = physics_signals(chip, params.window)
    mask = (i4 > params.i4_min) & (diff > params.diff_min) & (anom > params.anom_min)
    return (mask & valid_mask(chip)).astype(np.uint8)
