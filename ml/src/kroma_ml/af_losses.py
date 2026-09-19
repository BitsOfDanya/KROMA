import torch
import torch.nn.functional as F


def dice_loss(
    logits: torch.Tensor, targets: torch.Tensor, valid: torch.Tensor, eps: float = 1.0
) -> torch.Tensor:
    probs = torch.sigmoid(logits) * valid
    targets = targets * valid
    intersection = (probs * targets).sum(dim=(1, 2, 3))
    union = probs.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    dice = (2 * intersection + eps) / (union + eps)
    return 1 - dice.mean()


def bce_dice_loss(logits: torch.Tensor, targets: torch.Tensor, valid: torch.Tensor) -> torch.Tensor:
    bce = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    bce = (bce * valid).sum() / valid.sum().clamp_min(1.0)
    return bce + dice_loss(logits, targets, valid)


def focal_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    valid: torch.Tensor,
    alpha: float = 0.25,
    gamma: float = 2.0,
) -> torch.Tensor:
    probs = torch.sigmoid(logits)
    ce = F.binary_cross_entropy_with_logits(logits, targets, reduction="none")
    p_t = probs * targets + (1 - probs) * (1 - targets)
    alpha_t = alpha * targets + (1 - alpha) * (1 - targets)
    loss = alpha_t * (1 - p_t).pow(gamma) * ce
    return (loss * valid).sum() / valid.sum().clamp_min(1.0)


def focal_tversky_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    valid: torch.Tensor,
    alpha: float = 0.3,
    beta: float = 0.7,
    gamma: float = 1.33,
    eps: float = 1.0,
) -> torch.Tensor:
    probs = torch.sigmoid(logits) * valid
    targets = targets * valid
    tp = (probs * targets).sum(dim=(1, 2, 3))
    fp = (probs * (1 - targets)).sum(dim=(1, 2, 3))
    fn = ((1 - probs) * targets).sum(dim=(1, 2, 3))
    tversky = (tp + eps) / (tp + alpha * fp + beta * fn + eps)
    return (1 - tversky).pow(1 / gamma).mean()


LOSSES = {
    "bce_dice": bce_dice_loss,
    "focal": focal_loss,
    "focal_tversky": focal_tversky_loss,
}
