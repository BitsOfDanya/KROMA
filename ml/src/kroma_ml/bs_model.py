import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from kroma_ml.bs_data import BSChip
from kroma_ml.bs_features import bs_channel_stack


class ConvBlock(nn.Module):
    def __init__(self, ch_in: int, ch_out: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(ch_in, ch_out, kernel_size=3, padding=1, bias=True),
            nn.BatchNorm2d(ch_out),
            nn.ReLU(inplace=True),
            nn.Conv2d(ch_out, ch_out, kernel_size=3, padding=1, bias=True),
            nn.BatchNorm2d(ch_out),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class UpConvBlock(nn.Module):
    def __init__(self, ch_in: int, ch_out: int) -> None:
        super().__init__()
        self.up = nn.Sequential(
            nn.Upsample(scale_factor=2),
            nn.Conv2d(ch_in, ch_out, kernel_size=3, padding=1, bias=True),
            nn.BatchNorm2d(ch_out),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.up(x)


class AttentionBlock(nn.Module):
    def __init__(self, f_g: int, f_l: int, f_int: int) -> None:
        super().__init__()
        self.w_g = nn.Sequential(
            nn.Conv2d(f_g, f_int, kernel_size=1, bias=True), nn.BatchNorm2d(f_int)
        )
        self.w_x = nn.Sequential(
            nn.Conv2d(f_l, f_int, kernel_size=1, bias=True), nn.BatchNorm2d(f_int)
        )
        self.psi = nn.Sequential(
            nn.Conv2d(f_int, 1, kernel_size=1, bias=True), nn.BatchNorm2d(1), nn.Sigmoid()
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, g: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
        psi = self.relu(self.w_g(g) + self.w_x(x))
        return self.psi(psi) * x


class AttentionUNet(nn.Module):
    def __init__(self, in_channels: int, num_classes: int = 4, base: int = 32) -> None:
        super().__init__()
        self.maxpool = nn.MaxPool2d(kernel_size=2, stride=2)
        c1, c2, c3, c4, c5 = base, base * 2, base * 4, base * 8, base * 16
        self.conv1 = ConvBlock(in_channels, c1)
        self.conv2 = ConvBlock(c1, c2)
        self.conv3 = ConvBlock(c2, c3)
        self.conv4 = ConvBlock(c3, c4)
        self.conv5 = ConvBlock(c4, c5)

        self.up5 = UpConvBlock(c5, c4)
        self.att5 = AttentionBlock(c4, c4, c3)
        self.upconv5 = ConvBlock(c5, c4)

        self.up4 = UpConvBlock(c4, c3)
        self.att4 = AttentionBlock(c3, c3, c2)
        self.upconv4 = ConvBlock(c4, c3)

        self.up3 = UpConvBlock(c3, c2)
        self.att3 = AttentionBlock(c2, c2, c1)
        self.upconv3 = ConvBlock(c3, c2)

        self.up2 = UpConvBlock(c2, c1)
        self.att2 = AttentionBlock(c1, c1, base // 2)
        self.upconv2 = ConvBlock(c2, c1)

        self.head = nn.Conv2d(c1, num_classes, kernel_size=1)

    def features(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.conv1(x)
        x2 = self.conv2(self.maxpool(x1))
        x3 = self.conv3(self.maxpool(x2))
        x4 = self.conv4(self.maxpool(x3))
        x5 = self.conv5(self.maxpool(x4))

        d5 = self.up5(x5)
        x4 = self.att5(g=d5, x=x4)
        d5 = self.upconv5(torch.cat((x4, d5), dim=1))

        d4 = self.up4(d5)
        x3 = self.att4(g=d4, x=x3)
        d4 = self.upconv4(torch.cat((x3, d4), dim=1))

        d3 = self.up3(d4)
        x2 = self.att3(g=d3, x=x2)
        d3 = self.upconv3(torch.cat((x2, d3), dim=1))

        d2 = self.up2(d3)
        x1 = self.att2(g=d2, x=x1)
        return self.upconv2(torch.cat((x1, d2), dim=1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


class DualHeadAttentionUNet(AttentionUNet):
    def __init__(self, in_channels: int, base: int = 32) -> None:
        super().__init__(in_channels, num_classes=4, base=base)
        self.head = nn.Identity()
        self.burn_head = nn.Conv2d(base, 1, kernel_size=1)
        self.severity_head = nn.Conv2d(base, 3, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feats = self.features(x)
        return torch.cat([self.burn_head(feats), self.severity_head(feats)], dim=1)


def dual_to_class_logits(out: torch.Tensor) -> torch.Tensor:
    burn = out[:, :1]
    background = F.logsigmoid(-burn)
    severity = F.logsigmoid(burn) + F.log_softmax(out[:, 1:], dim=1)
    return torch.cat([background, severity], dim=1)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


class BSPredictor:
    def __init__(
        self,
        checkpoint_path: str,
        device: str | None = None,
        class_bias: np.ndarray | None = None,
    ) -> None:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        self.names: tuple[str, ...] = tuple(checkpoint["channel_names"])
        self.mean = checkpoint["normalization_mean"]
        self.std = checkpoint["normalization_std"]
        self.device = torch.device(device or "cpu")
        self.model = AttentionUNet(
            in_channels=len(self.names), base=checkpoint.get("base_channels", 32)
        )
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.to(self.device).eval()
        self.class_bias = (
            torch.from_numpy(np.asarray(class_bias, dtype=np.float32))
            if class_bias is not None
            else None
        )

    def predict_chip(self, chip: BSChip) -> np.ndarray:
        stack = bs_channel_stack(chip, self.names)
        normed = (stack - self.mean) / self.std
        x = torch.from_numpy(normed.transpose(2, 0, 1)).float().unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(x).squeeze(0)
            if self.class_bias is not None:
                logits = logits + self.class_bias.to(self.device)[:, None, None]
        return logits.argmax(dim=0).cpu().numpy().astype(np.uint8)
