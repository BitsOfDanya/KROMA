import numpy as np
from scipy import ndimage

from kroma_ml.bs_data import load_chip
from kroma_ml.bs_physics import _nd

RE_PIX = (
    "dB5",
    "dB6",
    "dB7",
    "dNDRE5",
    "dNDRE6",
    "dNDRE7",
    "NDRE7_post",
    "dB5_mean11",
    "dNDRE7_mean11",
)


def rededge_maps_root(cid: str, root: str) -> dict:
    chip = load_chip(cid, root=root, with_mask=False)

    def s(w, b):
        return chip.s2(w, b) / 10000.0

    out = {f"d{b}": s("post", b) - s("pre", b) for b in ("B5", "B6", "B7")}
    for i, b in ((5, "B5"), (6, "B6"), (7, "B7")):
        pre, post = _nd(s("pre", "B8A"), s("pre", b)), _nd(s("post", "B8A"), s("post", b))
        out[f"dNDRE{i}"] = pre - post
        if i == 7:
            out["NDRE7_post"] = post
    out["dB5_mean11"] = ndimage.uniform_filter(out["dB5"], 11)
    out["dNDRE7_mean11"] = ndimage.uniform_filter(out["dNDRE7"], 11)
    return out


def comp_stats(lab: np.ndarray, maps: list[np.ndarray]) -> np.ndarray:
    n = int(lab.max())
    if not n:
        return np.zeros((0, len(maps)), np.float32)
    idx = np.arange(1, n + 1)
    return np.stack([ndimage.mean(m, lab, idx) for m in maps], 1).astype(np.float32)


def ring_contrast(lab: np.ndarray, x: np.ndarray) -> np.ndarray:
    n = int(lab.max())
    if not n:
        return np.zeros(0, np.float32)
    idx = np.arange(1, n + 1)
    ring = ndimage.grey_dilation(lab, footprint=np.ones((11, 11)))
    ring = np.where(lab == 0, ring, 0)
    inner = ndimage.mean(x, lab, idx)
    outer = ndimage.sum(x, ring, idx) / np.maximum(ndimage.sum(np.ones_like(x), ring, idx), 1)
    return (inner - outer).astype(np.float32)
