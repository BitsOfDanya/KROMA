import torch
import torch.nn as nn
import torch.nn.functional as F

from kroma_ml.bs_losses import OHEMLoss

IGNORE_INDEX = 255


def class_soft_stats(
    logits: torch.Tensor, target: torch.Tensor, cls: int, ignore_index: int = IGNORE_INDEX
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    valid = (target != ignore_index).float()
    prob = F.softmax(logits, dim=1)[:, cls] * valid
    truth = (target == cls).float() * valid
    tp = (prob * truth).sum()
    return tp, (prob * (1 - truth)).sum(), ((1 - prob) * truth * valid).sum()


def soft_dice(logits: torch.Tensor, target: torch.Tensor, cls: int) -> torch.Tensor:
    tp, fp, fn = class_soft_stats(logits, target, cls)
    return 1 - (2 * tp + 1.0) / (2 * tp + fp + fn + 1.0)


def soft_tversky(
    logits: torch.Tensor, target: torch.Tensor, cls: int, alpha: float, beta: float
) -> torch.Tensor:
    tp, fp, fn = class_soft_stats(logits, target, cls)
    return 1 - (tp + 1.0) / (tp + alpha * fp + beta * fn + 1.0)


def lovasz_grad(gt_sorted: torch.Tensor) -> torch.Tensor:
    gts = gt_sorted.sum()
    intersection = gts - gt_sorted.cumsum(0)
    union = gts + (1 - gt_sorted).cumsum(0)
    jaccard = 1.0 - intersection / union
    if len(gt_sorted) > 1:
        jaccard[1:] = jaccard[1:] - jaccard[:-1]
    return jaccard


def lovasz_softmax(
    logits: torch.Tensor, target: torch.Tensor, ignore_index: int = IGNORE_INDEX
) -> torch.Tensor:
    probs = F.softmax(logits, dim=1)
    c = probs.shape[1]
    probs = probs.permute(0, 2, 3, 1).reshape(-1, c)
    labels = target.reshape(-1)
    keep = labels != ignore_index
    probs, labels = probs[keep], labels[keep]
    if labels.numel() == 0:
        return logits.sum() * 0.0
    losses = []
    for k in range(c):
        fg = (labels == k).float()
        if fg.sum() == 0:
            continue
        errors = (fg - probs[:, k]).abs()
        errors_sorted, perm = torch.sort(errors, descending=True)
        losses.append(torch.dot(errors_sorted, lovasz_grad(fg[perm])))
    return torch.stack(losses).mean() if losses else logits.sum() * 0.0


class TrackLoss(nn.Module):
    def __init__(
        self,
        kind: str,
        keep_ratio: float = 0.4,
        class_weights: torch.Tensor | None = None,
        aux_weight: float = 0.5,
        tversky: tuple[float, float] = (0.3, 0.7),
    ) -> None:
        super().__init__()
        if kind not in ("ohem", "ohem_dice1", "ohem_tversky1", "ohem_lovasz"):
            raise ValueError(kind)
        self.kind, self.aux_weight, self.tversky = kind, aux_weight, tversky
        self.ohem = OHEMLoss(keep_ratio, class_weights=class_weights)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        loss = self.ohem(logits, target)
        if self.kind == "ohem_dice1":
            loss = loss + self.aux_weight * soft_dice(logits, target, 1)
        elif self.kind == "ohem_tversky1":
            loss = loss + self.aux_weight * soft_tversky(logits, target, 1, *self.tversky)
        elif self.kind == "ohem_lovasz":
            loss = loss + self.aux_weight * lovasz_softmax(logits.float(), target)
        return loss
