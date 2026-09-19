import torch
import torch.nn as nn
import torch.nn.functional as F

IGNORE_INDEX = 255


class DiceLoss(nn.Module):
    def __init__(self, num_classes: int, smooth: float = 1e-6, ignore_index: int = IGNORE_INDEX):
        super().__init__()
        self.num_classes = num_classes
        self.smooth = smooth
        self.ignore_index = ignore_index

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        valid = target != self.ignore_index
        safe_target = target.clone()
        safe_target[~valid] = 0
        probs = F.softmax(logits, dim=1)
        target_oh = F.one_hot(safe_target, self.num_classes).permute(0, 3, 1, 2).float()
        valid_f = valid.unsqueeze(1).float()
        probs = probs * valid_f
        target_oh = target_oh * valid_f
        dims = (0, 2, 3)
        intersection = torch.sum(probs * target_oh, dims)
        cardinality = torch.sum(probs + target_oh, dims)
        dice = (2.0 * intersection + self.smooth) / (cardinality + self.smooth)
        return 1 - dice.mean()


class CombinedLoss(nn.Module):
    def __init__(
        self,
        class_weights: torch.Tensor | None,
        num_classes: int,
        ce_w: float = 0.5,
        dice_w: float = 0.5,
        ignore_index: int = IGNORE_INDEX,
    ):
        super().__init__()
        self.ce = nn.CrossEntropyLoss(weight=class_weights, ignore_index=ignore_index)
        self.dice = DiceLoss(num_classes, ignore_index=ignore_index)
        self.ce_w, self.dice_w = ce_w, dice_w

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return self.ce_w * self.ce(logits, target) + self.dice_w * self.dice(logits, target)


class BurnSeverityLoss(nn.Module):
    def __init__(self, class_weights: torch.Tensor | None, ignore_index: int = IGNORE_INDEX):
        super().__init__()
        self.ignore_index = ignore_index
        self.class_weights = class_weights

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        valid = target != self.ignore_index
        burn_target = (target > 0).float()
        burn_logit = torch.logsumexp(logits[:, 1:], dim=1) - torch.logsumexp(logits, dim=1)
        burn_loss = F.binary_cross_entropy_with_logits(burn_logit, burn_target, reduction="none")
        burn_loss = (burn_loss * valid).sum() / valid.sum().clamp_min(1.0)

        severity_valid = valid & (target > 0)
        if severity_valid.any():
            safe_target = target.clone()
            safe_target[~severity_valid] = 1
            severity_target = (safe_target - 1).clamp(min=0, max=2)
            severity_logits = logits[:, 1:]
            ce = F.cross_entropy(
                severity_logits, severity_target, weight=self.class_weights, reduction="none"
            )
            severity_loss = (ce * severity_valid).sum() / severity_valid.sum().clamp_min(1.0)
        else:
            severity_loss = logits.sum() * 0.0
        return burn_loss + severity_loss


class OHEMLoss(nn.Module):
    def __init__(
        self,
        keep_ratio: float = 0.4,
        class_weights: torch.Tensor | None = None,
        ignore_index: int = IGNORE_INDEX,
    ):
        super().__init__()
        if not 0.0 < keep_ratio <= 1.0:
            raise ValueError("keep_ratio must be in (0, 1]")
        self.keep_ratio = keep_ratio
        self.class_weights = class_weights
        self.ignore_index = ignore_index

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        pixel = F.cross_entropy(
            logits,
            target,
            weight=self.class_weights,
            ignore_index=self.ignore_index,
            reduction="none",
        )
        valid = pixel[target != self.ignore_index]
        if valid.numel() == 0:
            return logits.sum() * 0.0
        k = min(valid.numel(), max(1, int(valid.numel() * self.keep_ratio)))
        return torch.topk(valid, k, sorted=False).values.mean()


class DualHeadLoss(nn.Module):
    def __init__(self, ordinal_weight: float = 0.0, ignore_index: int = IGNORE_INDEX):
        super().__init__()
        self.ordinal_weight = ordinal_weight
        self.ignore_index = ignore_index

    def forward(self, out: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        valid = (target != self.ignore_index).float()
        burn_target = (target > 0).float() * valid
        burn_logit = out[:, 0]
        bce = F.binary_cross_entropy_with_logits(burn_logit, burn_target, reduction="none")
        bce = (bce * valid).sum() / valid.sum().clamp_min(1.0)
        prob = torch.sigmoid(burn_logit) * valid
        inter = (prob * burn_target).sum()
        union = prob.sum() + burn_target.sum() - inter
        loss = bce + (1.0 - (inter + 1.0) / (union + 1.0))

        sev_valid = (target > 0) & (target != self.ignore_index)
        if sev_valid.any():
            sev_target = (target.clamp(1, 3) - 1).long()
            ce = F.cross_entropy(out[:, 1:], sev_target, reduction="none")
            loss = loss + (ce * sev_valid).sum() / sev_valid.sum()
            if self.ordinal_weight > 0:
                expected = (
                    F.softmax(out[:, 1:], dim=1)
                    * torch.arange(3, device=out.device).view(1, 3, 1, 1)
                ).sum(1)
                ordinal = (expected - sev_target.float()).abs()
                loss = loss + self.ordinal_weight * (ordinal * sev_valid).sum() / sev_valid.sum()
        return loss
