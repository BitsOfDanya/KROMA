import math

import torch
import torch.nn as nn
import torch.nn.functional as F

from kroma_ml.bs_model import AttentionUNet

MODEL_NAMES = ("attunet", "segformer_b0", "mobileunet")


class OverlapPatchEmbed(nn.Module):
    def __init__(self, ch_in: int, dim: int, kernel: int, stride: int) -> None:
        super().__init__()
        self.proj = nn.Conv2d(ch_in, dim, kernel, stride, kernel // 2)
        self.norm = nn.LayerNorm(dim)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, int, int]:
        x = self.proj(x)
        _, _, h, w = x.shape
        return self.norm(x.flatten(2).transpose(1, 2)), h, w


class EfficientAttention(nn.Module):
    def __init__(self, dim: int, heads: int, sr: int) -> None:
        super().__init__()
        self.heads, self.scale = heads, (dim // heads) ** -0.5
        self.q = nn.Linear(dim, dim)
        self.kv = nn.Linear(dim, dim * 2)
        self.proj = nn.Linear(dim, dim)
        self.sr = nn.Conv2d(dim, dim, sr, sr) if sr > 1 else None
        self.norm = nn.LayerNorm(dim) if sr > 1 else None

    def forward(self, x: torch.Tensor, h: int, w: int) -> torch.Tensor:
        b, n, c = x.shape
        d = c // self.heads
        q = self.q(x).reshape(b, n, self.heads, d).transpose(1, 2)
        src = x
        if self.sr is not None:
            src = self.sr(x.transpose(1, 2).reshape(b, c, h, w)).flatten(2).transpose(1, 2)
            src = self.norm(src)
        kv = self.kv(src).reshape(b, -1, 2, self.heads, d).permute(2, 0, 3, 1, 4)
        attn = torch.softmax((q @ kv[0].transpose(-2, -1)) * self.scale, dim=-1)
        out = (attn @ kv[1]).transpose(1, 2).reshape(b, n, c)
        return self.proj(out)


class MixFFN(nn.Module):
    def __init__(self, dim: int, ratio: int = 4) -> None:
        super().__init__()
        hidden = dim * ratio
        self.fc1 = nn.Linear(dim, hidden)
        self.dw = nn.Conv2d(hidden, hidden, 3, 1, 1, groups=hidden)
        self.fc2 = nn.Linear(hidden, dim)

    def forward(self, x: torch.Tensor, h: int, w: int) -> torch.Tensor:
        b, n, _ = x.shape
        x = self.fc1(x)
        x = self.dw(x.transpose(1, 2).reshape(b, -1, h, w)).flatten(2).transpose(1, 2)
        return self.fc2(F.gelu(x))


class MiTBlock(nn.Module):
    def __init__(self, dim: int, heads: int, sr: int) -> None:
        super().__init__()
        self.n1, self.n2 = nn.LayerNorm(dim), nn.LayerNorm(dim)
        self.attn = EfficientAttention(dim, heads, sr)
        self.ffn = MixFFN(dim)

    def forward(self, x: torch.Tensor, h: int, w: int) -> torch.Tensor:
        x = x + self.attn(self.n1(x), h, w)
        return x + self.ffn(self.n2(x), h, w)


class SegFormer(nn.Module):
    def __init__(
        self,
        in_channels: int,
        num_classes: int = 4,
        dims: tuple[int, ...] = (32, 64, 160, 256),
        depths: tuple[int, ...] = (2, 2, 2, 2),
        heads: tuple[int, ...] = (1, 2, 5, 8),
        srs: tuple[int, ...] = (8, 4, 2, 1),
        decoder_dim: int = 256,
    ) -> None:
        super().__init__()
        self.embeds, self.stages, self.norms = nn.ModuleList(), nn.ModuleList(), nn.ModuleList()
        ch = in_channels
        for i, dim in enumerate(dims):
            k, s = (7, 4) if i == 0 else (3, 2)
            self.embeds.append(OverlapPatchEmbed(ch, dim, k, s))
            self.stages.append(
                nn.ModuleList(MiTBlock(dim, heads[i], srs[i]) for _ in range(depths[i]))
            )
            self.norms.append(nn.LayerNorm(dim))
            ch = dim
        self.lateral = nn.ModuleList(nn.Conv2d(d, decoder_dim, 1) for d in dims)
        self.fuse = nn.Sequential(
            nn.Conv2d(decoder_dim * len(dims), decoder_dim, 1, bias=False),
            nn.BatchNorm2d(decoder_dim),
            nn.ReLU(inplace=True),
            nn.Dropout2d(0.1),
        )
        self.head = nn.Conv2d(decoder_dim, num_classes, 1)
        self.apply(self._init)
        nn.init.normal_(self.head.weight, std=0.01)

    @staticmethod
    def _init(m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            nn.init.trunc_normal_(m.weight, std=0.02)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Conv2d):
            fan_out = m.kernel_size[0] * m.kernel_size[1] * m.out_channels // m.groups
            m.weight.data.normal_(0, math.sqrt(2.0 / fan_out))
            if m.bias is not None:
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        size = x.shape[-2:]
        feats = []
        for embed, blocks, norm in zip(self.embeds, self.stages, self.norms, strict=True):
            x, h, w = embed(x)
            for block in blocks:
                x = block(x, h, w)
            x = norm(x).transpose(1, 2).reshape(x.shape[0], -1, h, w)
            feats.append(x)
        target = feats[0].shape[-2:]
        ups = [
            F.interpolate(lat(f), size=target, mode="bilinear", align_corners=False)
            for lat, f in zip(self.lateral, feats, strict=True)
        ]
        out = self.head(self.fuse(torch.cat(ups, 1)))
        return F.interpolate(out, size=size, mode="bilinear", align_corners=False)


def conv_bn(ch_in: int, ch_out: int, k: int = 3, s: int = 1, groups: int = 1) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(ch_in, ch_out, k, s, k // 2, groups=groups, bias=False),
        nn.BatchNorm2d(ch_out),
        nn.ReLU6(inplace=True),
    )


class InvertedResidual(nn.Module):
    def __init__(self, ch_in: int, ch_out: int, stride: int, expand: int = 4) -> None:
        super().__init__()
        hidden = ch_in * expand
        self.use_res = stride == 1 and ch_in == ch_out
        self.block = nn.Sequential(
            conv_bn(ch_in, hidden, 1),
            conv_bn(hidden, hidden, 3, stride, groups=hidden),
            nn.Conv2d(hidden, ch_out, 1, bias=False),
            nn.BatchNorm2d(ch_out),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.block(x)
        return x + y if self.use_res else y


class MobileUNet(nn.Module):
    def __init__(
        self,
        in_channels: int,
        num_classes: int = 4,
        widths: tuple[int, ...] = (24, 32, 48, 96, 160),
    ) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            conv_bn(in_channels, widths[0]), InvertedResidual(widths[0], widths[0], 1)
        )
        self.down = nn.ModuleList(
            nn.Sequential(
                InvertedResidual(widths[i], widths[i + 1], 2),
                InvertedResidual(widths[i + 1], widths[i + 1], 1),
            )
            for i in range(len(widths) - 1)
        )
        self.up = nn.ModuleList(
            nn.Sequential(
                conv_bn(widths[i + 1] + widths[i], widths[i], 1),
                InvertedResidual(widths[i], widths[i], 1),
            )
            for i in reversed(range(len(widths) - 1))
        )
        self.head = nn.Conv2d(widths[0], num_classes, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        skips = [self.stem(x)]
        for down in self.down:
            skips.append(down(skips[-1]))
        y = skips.pop()
        for up in self.up:
            skip = skips.pop()
            y = F.interpolate(y, size=skip.shape[-2:], mode="bilinear", align_corners=False)
            y = up(torch.cat([y, skip], 1))
        return self.head(y)


def build_model(name: str, in_channels: int) -> nn.Module:
    if name == "attunet":
        return AttentionUNet(in_channels=in_channels, base=32)
    if name == "segformer_b0":
        return SegFormer(in_channels)
    if name == "mobileunet":
        return MobileUNet(in_channels)
    raise ValueError(name)
