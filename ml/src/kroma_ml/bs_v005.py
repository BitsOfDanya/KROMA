import numpy as np
from scipy import ndimage

EIGHT = np.ones((3, 3), dtype=bool)
DIST_BINS = (2, 5, 10, 20)


def severity_with_prior(probs: np.ndarray, org_sev: np.ndarray, weight: float = 1.0) -> np.ndarray:
    logp = np.log(np.maximum(probs[1:], 1e-8))
    org = np.clip(org_sev, 1, 3)
    onehot = np.stack([(org == c) for c in (1, 2, 3)]).astype(np.float32)
    return 1 + (logp + weight * onehot).argmax(0)


def compose_labels(burn: np.ndarray, probs: np.ndarray, org_sev: np.ndarray) -> np.ndarray:
    return np.where(burn, severity_with_prior(probs, org_sev), 0)


def distance_to(mask: np.ndarray, cap: float = 200.0) -> np.ndarray:
    if not mask.any():
        return np.full(mask.shape, cap, dtype=np.float32)
    return np.minimum(ndimage.distance_transform_edt(~mask), cap).astype(np.float32)


def clean_core(mask: np.ndarray, min_size: int) -> np.ndarray:
    lab, n = ndimage.label(mask, EIGHT)
    if not n:
        return mask
    sizes = np.bincount(lab.ravel())
    keep = sizes >= min_size
    keep[0] = False
    return keep[lab]


def hysteresis(p_burn: np.ndarray, t_high: float, t_low: float, radius: int = 0) -> np.ndarray:
    seeds = p_burn >= t_high
    cand = (p_burn >= t_low) | seeds
    if radius > 0:
        seeds = ndimage.binary_dilation(seeds, EIGHT, iterations=radius) & cand
    lab, n = ndimage.label(cand, EIGHT)
    if not n:
        return cand
    hit = np.zeros(n + 1, dtype=bool)
    hit[np.unique(lab[seeds])] = True
    hit[0] = False
    return hit[lab]


def distance_conditioned(
    p_burn: np.ndarray, dist_core: np.ndarray, near: float, t_near: float, t_far: float
) -> np.ndarray:
    return np.where(dist_core <= near, p_burn >= t_near, p_burn >= t_far)


def distance_histogram(dist: np.ndarray, sel: np.ndarray) -> np.ndarray:
    d = dist[sel]
    edges = (-1.0, *DIST_BINS, np.inf)
    return np.histogram(d, bins=edges)[0]
