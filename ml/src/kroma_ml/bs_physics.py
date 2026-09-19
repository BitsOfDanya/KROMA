from dataclasses import dataclass

import numpy as np

from kroma_ml.bs_metrics import NUM_CLASSES

INDEX_NAMES = (
    "nbr_pre",
    "nbr_post",
    "dnbr",
    "rdnbr",
    "rdnbr_b11",
    "ndvi_pre",
    "ndvi_post",
    "dndvi",
    "d_nir",
    "d_swir1",
    "d_swir2",
)
USGS_DNBR = (0.10, 0.27, 0.66)
MILLER_THODE_RDNBR = (0.069, 0.316, 0.641)
RDNBR_FLOOR = 1e-2


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / (a + b)
    return np.clip(np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0), -1.0, 1.0)


def relativized(dnbr: np.ndarray, nbr_pre: np.ndarray) -> np.ndarray:
    return np.clip(dnbr / (np.sqrt(np.abs(nbr_pre)) + RDNBR_FLOOR), -6.0, 6.0)


def spectral_indices(refl: np.ndarray) -> dict[str, np.ndarray]:
    pre_red, pre_nir, pre_swir1, pre_swir2, post_red, post_nir, post_swir1, post_swir2 = refl
    nbr_pre, nbr_post = _nd(pre_nir, pre_swir2), _nd(post_nir, post_swir2)
    nbr1_pre, nbr1_post = _nd(pre_nir, pre_swir1), _nd(post_nir, post_swir1)
    ndvi_pre, ndvi_post = _nd(pre_nir, pre_red), _nd(post_nir, post_red)
    dnbr = nbr_pre - nbr_post
    return {
        "nbr_pre": nbr_pre,
        "nbr_post": nbr_post,
        "dnbr": dnbr,
        "rdnbr": relativized(dnbr, nbr_pre),
        "rdnbr_b11": relativized(nbr1_pre - nbr1_post, nbr1_pre),
        "ndvi_pre": ndvi_pre,
        "ndvi_post": ndvi_post,
        "dndvi": ndvi_pre - ndvi_post,
        "d_nir": post_nir - pre_nir,
        "d_swir1": post_swir1 - pre_swir1,
        "d_swir2": post_swir2 - pre_swir2,
    }


def threshold_classes(index: np.ndarray, thresholds: tuple[float, ...]) -> np.ndarray:
    return np.digitize(index, np.asarray(thresholds, dtype=np.float64)).astype(np.int64)


def gated_classes(
    gate: np.ndarray, gate_t: float, severity: np.ndarray, sev_t: tuple[float, float]
) -> np.ndarray:
    sev = 1 + np.digitize(severity, np.asarray(sev_t, dtype=np.float64))
    return np.where(gate > gate_t, sev, 0).astype(np.int64)


def bs_from_confusion(cm: np.ndarray) -> np.ndarray:
    cm = np.asarray(cm, dtype=np.float64)
    tp = np.diagonal(cm, axis1=-2, axis2=-1)
    union = cm.sum(-1) + cm.sum(-2) - tp
    iou = np.divide(tp, union, out=np.zeros_like(tp), where=union > 0)
    burn_tp = cm[..., 1:, 1:].sum((-1, -2))
    burn_union = cm[..., 1:, :].sum((-1, -2)) + cm[..., :, 1:].sum((-1, -2)) - burn_tp
    burn = np.divide(burn_tp, burn_union, out=np.zeros_like(burn_tp), where=burn_union > 0)
    return 0.35 * burn + 0.30 * iou[..., 1:].mean(-1)


@dataclass
class Hist1D:
    edges: np.ndarray
    counts: np.ndarray

    @classmethod
    def empty(cls, lo: float, hi: float, bins: int) -> "Hist1D":
        return cls(np.linspace(lo, hi, bins + 1), np.zeros((NUM_CLASSES, bins), dtype=np.int64))

    def add(self, values: np.ndarray, labels: np.ndarray) -> None:
        b = np.clip(np.searchsorted(self.edges, values, side="right") - 1, 0, len(self.edges) - 2)
        flat = labels.astype(np.int64) * (len(self.edges) - 1) + b
        self.counts += np.bincount(flat, minlength=self.counts.size).reshape(self.counts.shape)


@dataclass
class Hist2D:
    edges_a: np.ndarray
    edges_b: np.ndarray
    counts: np.ndarray

    @classmethod
    def empty(cls, a: tuple[float, float, int], b: tuple[float, float, int]) -> "Hist2D":
        ea, eb = np.linspace(a[0], a[1], a[2] + 1), np.linspace(b[0], b[1], b[2] + 1)
        return cls(ea, eb, np.zeros((NUM_CLASSES, a[2], b[2]), dtype=np.int64))

    def add(self, va: np.ndarray, vb: np.ndarray, labels: np.ndarray) -> None:
        na, nb = len(self.edges_a) - 1, len(self.edges_b) - 1
        ia = np.clip(np.searchsorted(self.edges_a, va, side="right") - 1, 0, na - 1)
        ib = np.clip(np.searchsorted(self.edges_b, vb, side="right") - 1, 0, nb - 1)
        flat = (labels.astype(np.int64) * na + ia) * nb + ib
        self.counts += np.bincount(flat, minlength=self.counts.size).reshape(self.counts.shape)


def fit_thresholds_1d(hist: Hist1D, step: int = 1) -> tuple[tuple[float, float, float], float]:
    cum = np.concatenate([np.zeros((NUM_CLASSES, 1)), np.cumsum(hist.counts, axis=1)], axis=1)
    cand = np.arange(0, cum.shape[1], step)
    best, best_t = -1.0, (0, 0, 0)
    total = cum[:, -1]
    for i3 in cand:
        i1, i2 = np.meshgrid(cand[cand <= i3], cand[cand <= i3], indexing="ij")
        keep = i1 <= i2
        i1, i2 = i1[keep], i2[keep]
        c0 = cum[:, i1]
        c1 = cum[:, i2] - cum[:, i1]
        c2 = cum[:, [i3]] - cum[:, i2]
        c3 = (total - cum[:, i3])[:, None] * np.ones_like(c0)
        cm = np.stack([c0, c1, c2, c3], axis=-1).transpose(1, 0, 2)
        s = bs_from_confusion(cm)
        j = int(np.argmax(s))
        if s[j] > best:
            best, best_t = float(s[j]), (int(i1[j]), int(i2[j]), int(i3))
    e = hist.edges
    return (float(e[best_t[0]]), float(e[best_t[1]]), float(e[best_t[2]])), best


def fit_gated(hist: Hist2D, step: int = 1) -> tuple[tuple[float, float, float], float]:
    counts = hist.counts
    ca = np.concatenate(
        [np.zeros((NUM_CLASSES, 1, counts.shape[2])), np.cumsum(counts, axis=1)], axis=1
    )
    total_a = ca[:, -1:, :]
    best, best_t = -1.0, (0, 0, 0)
    na, nb = counts.shape[1], counts.shape[2]
    cand_b = np.arange(0, nb + 1, step)
    for ig in range(0, na + 1, step):
        below = ca[:, ig, :].sum(-1)
        above = total_a[:, 0, :] - ca[:, ig, :]
        cb = np.concatenate([np.zeros((NUM_CLASSES, 1)), np.cumsum(above, axis=1)], axis=1)
        i1, i2 = np.meshgrid(cand_b, cand_b, indexing="ij")
        keep = i1 <= i2
        i1, i2 = i1[keep], i2[keep]
        s1 = cb[:, i1]
        s2 = cb[:, i2] - cb[:, i1]
        s3 = cb[:, [-1]] - cb[:, i2]
        c0 = below[:, None] * np.ones_like(s1)
        cm = np.stack([c0, s1, s2, s3], axis=-1).transpose(1, 0, 2)
        s = bs_from_confusion(cm)
        j = int(np.argmax(s))
        if s[j] > best:
            best, best_t = float(s[j]), (ig, int(i1[j]), int(i2[j]))
    return (
        float(hist.edges_a[best_t[0]]),
        float(hist.edges_b[best_t[1]]),
        float(hist.edges_b[best_t[2]]),
    ), best


def class_stats(hist: Hist1D) -> list[dict]:
    centers = 0.5 * (hist.edges[1:] + hist.edges[:-1])
    out = []
    for c in range(NUM_CLASSES):
        h = hist.counts[c].astype(np.float64)
        n = h.sum()
        if n == 0:
            out.append({"n": 0})
            continue
        mean = float((h * centers).sum() / n)
        std = float(np.sqrt(max((h * (centers - mean) ** 2).sum() / n, 0.0)))
        cdf = np.cumsum(h) / n
        q = {f"p{p}": float(np.interp(p / 100, cdf, hist.edges[1:])) for p in (10, 25, 50, 75, 90)}
        out.append({"n": int(n), "mean": mean, "std": std, **q})
    return out


def pairwise_separability(hist: Hist1D, a: int, b: int) -> dict:
    ha, hb = hist.counts[a].astype(np.float64), hist.counts[b].astype(np.float64)
    if ha.sum() == 0 or hb.sum() == 0:
        return {"overlap": float("nan"), "auc": float("nan"), "bayes_err": float("nan")}
    pa, pb = ha / ha.sum(), hb / hb.sum()
    below_a = np.concatenate([[0.0], np.cumsum(pa)[:-1]])
    auc = float((pb * (below_a + 0.5 * pa)).sum())
    return {
        "overlap": float(np.minimum(pa, pb).sum()),
        "auc": auc,
        "bayes_err": float(0.5 * np.minimum(pa, pb).sum()),
    }
