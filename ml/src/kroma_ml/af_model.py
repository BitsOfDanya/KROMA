import numpy as np

from kroma_ml.af_data import load_chip, valid_mask
from kroma_ml.af_features import cached_feature_stack


def sample_training_pixels(
    chip_ids: list[str],
    neg_per_chip: int = 400,
    seed: int = 42,
    extra_negatives: dict[str, list[tuple[int, int]]] | None = None,
    feature_indices: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    feats: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    groups: list[np.ndarray] = []
    for chip_id in chip_ids:
        chip = load_chip(chip_id)
        if chip.mask is None:
            continue
        stack = cached_feature_stack(chip_id)
        valid = valid_mask(chip)
        fire = (chip.mask == 1) & valid
        bg = (chip.mask == 0) & valid
        fy, fx = np.nonzero(fire)
        by, bx = np.nonzero(bg)
        take = min(neg_per_chip, len(by))
        if take > 0:
            pick = rng.choice(len(by), size=take, replace=False)
            by, bx = by[pick], bx[pick]
        else:
            by, bx = np.array([], dtype=int), np.array([], dtype=int)
        if extra_negatives and chip_id in extra_negatives:
            extra = extra_negatives[chip_id]
            ey = np.array([p[0] for p in extra], dtype=int)
            ex = np.array([p[1] for p in extra], dtype=int)
            by = np.concatenate([by, ey])
            bx = np.concatenate([bx, ex])
        ys = np.concatenate([fy, by])
        xs = np.concatenate([fx, bx])
        ylab = np.concatenate([np.ones(len(fy), dtype=np.int8), np.zeros(len(by), dtype=np.int8)])
        chip_feats = stack[ys, xs]
        if feature_indices is not None:
            chip_feats = chip_feats[:, feature_indices]
        feats.append(chip_feats)
        labels.append(ylab)
        groups.append(np.full(len(ys), chip_id))
    return np.concatenate(feats), np.concatenate(labels), np.concatenate(groups)


def predict_chip_proba(
    model, chip_id: str, feature_indices: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    chip = load_chip(chip_id, with_mask=False)
    stack = cached_feature_stack(chip_id)
    valid = valid_mask(chip)
    h, w, c = stack.shape
    flat = stack.reshape(-1, c)
    if feature_indices is not None:
        flat = flat[:, feature_indices]
    proba = model.predict_proba(flat)[:, 1].reshape(h, w)
    proba = np.where(valid, proba, 0.0)
    return proba, valid
