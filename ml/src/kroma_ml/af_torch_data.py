from dataclasses import dataclass

import numpy as np
import torch
from torch.utils.data import Dataset

from kroma_ml.af_data import load_chip, valid_mask
from kroma_ml.af_features import cached_unet_stack

NO_NORMALIZE = {"valid", "landcover"}


@dataclass(frozen=True)
class ChannelStats:
    names: tuple[str, ...]
    mean: np.ndarray
    std: np.ndarray


def compute_channel_stats(chip_ids: list[str], names: tuple[str, ...]) -> ChannelStats:
    if not chip_ids or not names:
        raise ValueError("train chip IDs and channel names are required")
    sums = np.zeros(len(names), dtype=np.float64)
    sq_sums = np.zeros(len(names), dtype=np.float64)
    counts = np.zeros(len(names), dtype=np.float64)
    for chip_id in chip_ids:
        chip = load_chip(chip_id)
        stack = cached_unet_stack(chip_id, names)
        valid = valid_mask(chip)
        for i in range(len(names)):
            if names[i] in NO_NORMALIZE:
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
    return ChannelStats(names=names, mean=mean.astype(np.float32), std=std.astype(np.float32))


def normalize(stack: np.ndarray, stats: ChannelStats) -> np.ndarray:
    if stack.ndim != 3 or stack.shape[-1] != len(stats.names):
        raise ValueError("channel stack does not match normalization stats")
    result = (stack - stats.mean) / stats.std
    if "landcover" in stats.names:
        index = stats.names.index("landcover")
        result[..., index] = np.clip(stack[..., index], 0, 100) / 100
    return result


class AFChipDataset(Dataset):
    def __init__(
        self,
        chip_ids: list[str],
        stats: ChannelStats,
        positive_oversample: int = 3,
        augment: bool = False,
        extra_counts: dict[str, int] | None = None,
    ) -> None:
        self.chip_ids = chip_ids
        self.stats = stats
        self.augment = augment
        self.positives = []
        self.negatives = []
        for chip_id in chip_ids:
            chip = load_chip(chip_id)
            if chip.mask is not None and (chip.mask == 1).any():
                self.positives.append(chip_id)
            else:
                self.negatives.append(chip_id)
        self.index = self.positives * positive_oversample + self.negatives
        if extra_counts:
            for chip_id, count in extra_counts.items():
                self.index.extend([chip_id] * count)

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        chip_id = self.index[idx]
        chip = load_chip(chip_id)
        stack = cached_unet_stack(chip_id, self.stats.names)
        if stack.shape != (256, 256, len(self.stats.names)):
            raise ValueError("AF chip channel stack must be 256x256xC")
        stack = normalize(stack, self.stats)
        valid = valid_mask(chip).astype(np.float32)
        mask = (chip.mask == 1).astype(np.float32)
        if self.augment:
            if np.random.rand() < 0.5:
                stack = np.ascontiguousarray(stack[:, ::-1])
                valid = np.ascontiguousarray(valid[:, ::-1])
                mask = np.ascontiguousarray(mask[:, ::-1])
            if np.random.rand() < 0.5:
                stack = np.ascontiguousarray(stack[::-1, :])
                valid = np.ascontiguousarray(valid[::-1, :])
                mask = np.ascontiguousarray(mask[::-1, :])
        x = torch.from_numpy(stack.transpose(2, 0, 1)).float()
        y = torch.from_numpy(mask).float().unsqueeze(0)
        v = torch.from_numpy(valid).float().unsqueeze(0)
        return x, y, v


def load_full_chip_tensor(
    chip_id: str, stats: ChannelStats
) -> tuple[torch.Tensor, np.ndarray, np.ndarray]:
    chip = load_chip(chip_id, with_mask=True)
    stack = normalize(cached_unet_stack(chip_id, stats.names), stats)
    if stack.shape != (256, 256, len(stats.names)):
        raise ValueError("AF chip channel stack must be 256x256xC")
    valid = valid_mask(chip)
    true = chip.mask == 1 if chip.mask is not None else np.zeros(valid.shape, dtype=bool)
    x = torch.from_numpy(stack.transpose(2, 0, 1)).float().unsqueeze(0)
    return x, true, valid
