import json
from pathlib import Path

import numpy as np
from scipy import ndimage

from kroma_ml.bs_crop import RawChip
from kroma_ml.bs_physics import spectral_indices

GROUP_ORDER = ("forest_shrub", "grassland", "cropland", "wetland_floodplain")
FALLBACK_GROUP = "wetland_floodplain"
V003_BIAS = np.array([0.0, 0.4, 0.2, 0.2], dtype=np.float32)
FEATURES = (
    "p0", "p1", "p2", "p3", "p_burn", "m10", "top_margin", "pred",
    "dnbr", "rdnbr", "d_low", "d_mod", "d_high", "abs_d_low", "org_sev", "lc_group",
    "ndvi_pre", "ndvi_post", "dndvi",
    "pre_red", "pre_nir", "pre_swir1", "pre_swir2",
    "post_red", "post_nir", "post_swir1", "post_swir2",
    "scl_pre", "scl_post",
    "pburn_mean5", "pburn_mean15", "pburn_mean31", "p1_mean5", "dnbr_mean5", "dnbr_mean15",
    "orgburn_mean15", "dist_pred_boundary",
)  # fmt: skip
CATEGORICAL = ("pred", "lc_group", "scl_pre", "scl_post", "org_sev")


def load_thresholds(path: Path) -> dict:
    cfg = json.loads(Path(path).read_text())["groups"]
    table = np.array(
        [
            [cfg[g][k] for k in ("threshold_0_1", "threshold_1_2", "threshold_2_3")]
            for g in GROUP_ORDER
        ],
        dtype=np.float32,
    )
    codes = {c: GROUP_ORDER.index(g) for g in GROUP_ORDER for c in cfg[g]["worldcover"]}
    return {"table": table, "codes": codes}


def group_map(landcover: np.ndarray, th: dict) -> np.ndarray:
    out = np.full(landcover.shape, GROUP_ORDER.index(FALLBACK_GROUP), dtype=np.int64)
    for code, gi in th["codes"].items():
        out[landcover == code] = gi
    return out


def threshold_map(landcover: np.ndarray, th: dict) -> np.ndarray:
    return th["table"][group_map(landcover, th)].transpose(2, 0, 1)


def organizer_severity(dnbr: np.ndarray, tmap: np.ndarray) -> np.ndarray:
    return (dnbr[None] > tmap).sum(0).astype(np.int64)


def v003_logits(ndvi_logits: np.ndarray, dual_logits: np.ndarray) -> np.ndarray:
    blend = 0.5 * ndvi_logits.astype(np.float32) + 0.5 * dual_logits.astype(np.float32)
    return blend + V003_BIAS[:, None, None]


def softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(0, keepdims=True)
    e = np.exp(z)
    return e / e.sum(0, keepdims=True)


def signed_boundary_distance(burn: np.ndarray, cap: float = 50.0) -> np.ndarray:
    if not burn.any():
        return np.full(burn.shape, -cap, dtype=np.float32)
    if burn.all():
        return np.full(burn.shape, cap, dtype=np.float32)
    inside = ndimage.distance_transform_edt(burn)
    outside = ndimage.distance_transform_edt(~burn)
    return np.clip(np.where(burn, inside, -outside), -cap, cap).astype(np.float32)


def pixel_features(raw: RawChip, logits: np.ndarray, th: dict) -> dict[str, np.ndarray]:
    probs = softmax(logits)
    pred = probs.argmax(0)
    srt = np.sort(probs, 0)
    idx = spectral_indices(raw.refl)
    tmap = threshold_map(raw.landcover, th)
    org = organizer_severity(idx["dnbr"], tmap)
    p_burn = 1.0 - probs[0]
    f = {
        "p0": probs[0], "p1": probs[1], "p2": probs[2], "p3": probs[3], "p_burn": p_burn,
        "m10": probs[1] - probs[0], "top_margin": srt[-1] - srt[-2], "pred": pred,
        "dnbr": idx["dnbr"], "rdnbr": idx["rdnbr"],
        "d_low": idx["dnbr"] - tmap[0], "d_mod": idx["dnbr"] - tmap[1],
        "d_high": idx["dnbr"] - tmap[2],
        "abs_d_low": np.abs(idx["dnbr"] - tmap[0]), "org_sev": org,
        "lc_group": group_map(raw.landcover, th),
        "ndvi_pre": idx["ndvi_pre"], "ndvi_post": idx["ndvi_post"], "dndvi": idx["dndvi"],
        "scl_pre": raw.scl_pre, "scl_post": raw.scl_post,
        "pburn_mean5": ndimage.uniform_filter(p_burn, 5),
        "pburn_mean15": ndimage.uniform_filter(p_burn, 15),
        "pburn_mean31": ndimage.uniform_filter(p_burn, 31),
        "p1_mean5": ndimage.uniform_filter(probs[1], 5),
        "dnbr_mean5": ndimage.uniform_filter(idx["dnbr"], 5),
        "dnbr_mean15": ndimage.uniform_filter(idx["dnbr"], 15),
        "orgburn_mean15": ndimage.uniform_filter((org > 0).astype(np.float32), 15),
        "dist_pred_boundary": signed_boundary_distance(pred > 0),
    }  # fmt: skip
    names = (
        "pre_red",
        "pre_nir",
        "pre_swir1",
        "pre_swir2",
        "post_red",
        "post_nir",
        "post_swir1",
        "post_swir2",
    )
    f.update(dict(zip(names, raw.refl, strict=True)))
    return f


def refine_gate(f: dict, band: float, radius: float, keep_conf: float) -> np.ndarray:
    uncertain = (f["p_burn"] >= band) & (f["p_burn"] <= 1.0 - band)
    near = np.abs(f["dist_pred_boundary"]) <= radius
    confident_severe = (f["pred"] >= 2) & (np.maximum(f["p2"], f["p3"]) >= keep_conf)
    return (uncertain | near) & ~confident_severe


def stack(f: dict, sel: np.ndarray) -> np.ndarray:
    return np.stack([np.asarray(f[n])[sel].astype(np.float32) for n in FEATURES], 1)
