import numpy as np
from scipy.ndimage import label


def remove_small_components(mask: np.ndarray, min_size: int) -> np.ndarray:
    if min_size <= 1:
        return mask
    labeled, n = label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask
    sizes = np.bincount(labeled.ravel())
    keep = sizes >= min_size
    keep[0] = False
    return keep[labeled].astype(mask.dtype)
