from dataclasses import dataclass

import numpy as np
import torch
from torch.utils.data import Dataset

from kroma_ml.bs_data import IGNORE_INDEX, SCL_INVALID, load_chip, valid_mask
from kroma_ml.bs_features import cached_bs_stack

NO_NORMALIZE = {"landcover"}


@dataclass(frozen=True)
class BSChannelStats:
    names: tuple[str, ...]
    mean: np.ndarray
    std: np.ndarray


def compute_channel_stats(
    chip_ids: list[str], names: tuple[str, ...], invalid_codes: frozenset[int] = SCL_INVALID
) -> BSChannelStats:
    sums = np.zeros(len(names), dtype=np.float64)
    sq_sums = np.zeros(len(names), dtype=np.float64)
    counts = np.zeros(len(names), dtype=np.float64)
    for chip_id in chip_ids:
        chip = load_chip(chip_id)
        stack = cached_bs_stack(chip_id, names)
        valid = valid_mask(chip, invalid_codes)
        for i, name in enumerate(names):
            if name in NO_NORMALIZE:
                continue
            values = stack[..., i][valid]
            sums[i] += values.sum()
            sq_sums[i] += (values * values).sum()
            counts[i] += values.size
    mean = sums / np.maximum(counts, 1)
    var = sq_sums / np.maximum(counts, 1) - mean * mean
    std = np.sqrt(np.maximum(var, 1e-8))
    for i, name in enumerate(names):
        if name in NO_NORMALIZE:
            mean[i], std[i] = 0.0, 1.0
    return BSChannelStats(names=names, mean=mean.astype(np.float32), std=std.astype(np.float32))


def normalize(stack: np.ndarray, stats: BSChannelStats) -> np.ndarray:
    return (stack - stats.mean) / stats.std


class BSChipDataset(Dataset):
    def __init__(
        self,
        chip_ids: list[str],
        stats: BSChannelStats,
        augment: bool = False,
        invalid_codes: frozenset[int] = SCL_INVALID,
    ) -> None:
        self.chip_ids = chip_ids
        self.stats = stats
        self.augment = augment
        self.invalid_codes = invalid_codes

    def __len__(self) -> int:
        return len(self.chip_ids)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        chip_id = self.chip_ids[idx]
        chip = load_chip(chip_id)
        stack = normalize(cached_bs_stack(chip_id, self.stats.names), self.stats)
        valid = valid_mask(chip, self.invalid_codes)
        mask = chip.mask.astype(np.int64)
        mask = np.where(valid, mask, IGNORE_INDEX)
        if self.augment:
            k = np.random.randint(0, 4)
            if k:
                stack = np.ascontiguousarray(np.rot90(stack, k, axes=(0, 1)))
                mask = np.ascontiguousarray(np.rot90(mask, k, axes=(0, 1)))
            if np.random.rand() < 0.5:
                stack = np.ascontiguousarray(stack[:, ::-1])
                mask = np.ascontiguousarray(mask[:, ::-1])
        x = torch.from_numpy(stack.transpose(2, 0, 1)).float()
        y = torch.from_numpy(mask).long()
        return x, y


def class_weights(
    chip_ids: list[str], num_classes: int = 4, invalid_codes: frozenset[int] = SCL_INVALID
) -> torch.Tensor:
    counts = np.zeros(num_classes, dtype=np.int64)
    for chip_id in chip_ids:
        chip = load_chip(chip_id)
        valid = valid_mask(chip, invalid_codes)
        counts += np.bincount(chip.mask[valid].astype(np.int64), minlength=num_classes)
    weights = counts.sum() / (num_classes * np.maximum(counts, 1))
    weights = weights / weights.mean()
    return torch.tensor(weights, dtype=torch.float32)
