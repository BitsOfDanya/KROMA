import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

SEED = 42


def group_key(meta: pd.DataFrame) -> pd.Series:
    if meta["fire_event_id"].notna().any():
        key = meta["fire_event_id"].astype(str)
        key = key.where(meta["fire_event_id"].notna(), other=None)
    else:
        key = pd.Series([None] * len(meta), index=meta.index)
    tile = (
        meta["x_min"].astype(str)
        + "_"
        + meta["y_min"].astype(str)
        + "_"
        + meta["x_max"].astype(str)
        + "_"
        + meta["y_max"].astype(str)
    )
    return key.fillna(tile)


def train_val_split(
    meta: pd.DataFrame, val_size: float = 0.2, seed: int = SEED
) -> tuple[np.ndarray, np.ndarray]:
    groups = group_key(meta)
    splitter = GroupShuffleSplit(n_splits=1, test_size=val_size, random_state=seed)
    train_idx, val_idx = next(splitter.split(meta, groups=groups))
    train_ids = meta["chip_id"].to_numpy()[train_idx]
    val_ids = meta["chip_id"].to_numpy()[val_idx]
    overlap = set(groups.iloc[train_idx]) & set(groups.iloc[val_idx])
    if overlap:
        raise RuntimeError(f"group leakage between train/val: {overlap}")
    return train_ids, val_ids
