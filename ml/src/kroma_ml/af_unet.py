import numpy as np
import torch
from torch import nn

from kroma_ml.af_data import Chip


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.body(x)


class ResConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.bn1 = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU(inplace=True)
        self.skip = nn.Conv2d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.skip(x)
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.relu(out + residual)


class SmallUNet(nn.Module):
    def __init__(self, in_channels: int, base: int = 16, residual: bool = False) -> None:
        super().__init__()
        block = ResConvBlock if residual else ConvBlock
        self.enc1 = block(in_channels, base)
        self.enc2 = block(base, base * 2)
        self.enc3 = block(base * 2, base * 4)
        self.bottleneck = block(base * 4, base * 8)
        self.pool = nn.MaxPool2d(2)
        self.up3 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.dec3 = block(base * 8, base * 4)
        self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.dec2 = block(base * 4, base * 2)
        self.up1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.dec1 = block(base * 2, base)
        self.head = nn.Conv2d(base, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.head(d1)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


class AFUNetPredictor:
    def __init__(self, checkpoint_path: str, device: str | None = None) -> None:
        from kroma_ml.af_torch_data import ChannelStats

        selected = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        if selected == "mps" and not torch.backends.mps.is_available():
            selected = "cpu"
        self.device = torch.device(selected)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        self.names = tuple(checkpoint["channel_names"])
        self.stats = ChannelStats(
            self.names,
            np.asarray(checkpoint["normalization_mean"], dtype=np.float32),
            np.asarray(checkpoint["normalization_std"], dtype=np.float32),
        )
        self.threshold = float(checkpoint["threshold"])
        self.model = SmallUNet(
            len(self.names),
            base=int(checkpoint["base_channels"]),
            residual=bool(checkpoint["residual"]),
        ).to(self.device)
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()

    def predict_chip_proba(self, chip: Chip) -> np.ndarray:
        from kroma_ml.af_data import valid_mask
        from kroma_ml.af_features import unet_channel_stack
        from kroma_ml.af_torch_data import normalize

        stack = normalize(unet_channel_stack(chip, self.names), self.stats)
        if stack.shape != (256, 256, len(self.names)):
            raise ValueError("AF chip channel stack must be 256x256xC")
        tensor = torch.from_numpy(stack.transpose(2, 0, 1))[None].float().to(self.device)
        with torch.inference_mode():
            probabilities = torch.sigmoid(self.model(tensor))[0, 0].cpu().numpy()
        return np.where(valid_mask(chip), probabilities, 0.0)

    def predict_chip(self, chip: Chip) -> np.ndarray:
        return (self.predict_chip_proba(chip) >= self.threshold).astype(np.uint8)
