import lightgbm as lgb
import numpy as np
from scipy import ndimage

from kroma_ml.bs_cv import valid_mask
from kroma_ml.bs_physics import spectral_indices
from kroma_ml.bs_v004 import (
    group_map,
    organizer_severity,
    refine_gate,
    signed_boundary_distance,
    softmax,
    stack,
    threshold_map,
)
from kroma_ml.bs_v005 import EIGHT, clean_core, distance_to

CAND_T = 0.5
COMP_FEATURES = (
    "log_area",
    "perimeter_ratio",
    "compactness",
    "bbox_aspect",
    "fill_ratio",
    "p_mean",
    "p_max",
    "p_q90",
    "dnbr_mean",
    "dnbr_max",
    "dnbr_q90",
    "d_low_mean",
    "frac_sev2",
    "frac_sev3",
    "frac_org2",
    "frac_org3",
    "frac_crop",
    "frac_grass",
    "frac_forest",
    "frac_wet",
    "rank_area",
    "rank_sev3",
    "share_chip_burn",
    "dist_main_area",
    "dist_main_sev3",
    "n_components",
    "chip_burn_frac",
    "chip_dnbr_q90",
    "centroid_r",
    "touches_border",
    "ring_dnbr_mean",
    "ring_p_mean",
    "ring_org1_frac",
    "contrast_dnbr",
)
COMP05 = (
    "log_area",
    "dist_main_sev3",
    "share_chip_burn",
    "frac_sev3",
    "rank_sev3",
    "p_mean",
    "compactness",
    "ring_org1_frac",
    "contrast_dnbr",
    "dist_main_area",
    "rank_area",
)
COMP03 = ("log_area", "dist_main_sev3", "share_chip_burn", "p_mean", "frac_sev3")
PIX = (
    "p0",
    "p1",
    "p2",
    "p3",
    "p_burn",
    "pred",
    "dnbr",
    "rdnbr",
    "d_low",
    "d_mod",
    "org",
    "lc",
    "ndvi_post",
    "dndvi",
    "scl_pre",
    "scl_post",
    "dnbr_mean11",
    "dnbr_std11",
    "dnbr_mean41",
    "dnbr_std41",
    "pb_mean11",
    "pb_max11",
    "pb_mean41",
    "pb_max41",
    "org1_frac11",
    "org1_frac41",
    "dlow_min11",
    "samelc_frac41",
    "dist_boundary",
    "dist_main_sev3_px",
    "dist_main_area_px",
    "dist_core",
    "chip_burn_frac",
    "chip_n_comp",
    "chip_dnbr_q90",
)
FEATURES = PIX + tuple(f"c05_{n}" for n in COMP05) + tuple(f"c03_{n}" for n in COMP03)
CATEGORICAL = ("pred", "org", "lc", "scl_pre", "scl_post")
ZONE_P, ZONE_R = 0.15, 10.0
WIDE = {"band": 0.03, "radius": 6.0, "keep_conf": 0.6}
V004_BIAS = np.array([0.0, 0.4, 1.0, 0.8], dtype=np.float32)
BAND, RADIUS = 0.3, 2.0


def component_table(p_burn, pred, dnbr, dlow, org, lc, valid, cand_t=CAND_T):
    cand = (p_burn >= cand_t) & valid
    lab, n = ndimage.label(cand, EIGHT)
    if not n:
        return lab, np.zeros((0, len(COMP_FEATURES)), np.float32)
    idx = np.arange(1, n + 1)
    area = ndimage.sum(np.ones_like(p_burn), lab, idx)
    edge = cand & ~ndimage.binary_erosion(cand, EIGHT)
    perim = ndimage.sum(edge, lab, idx)
    sl = ndimage.find_objects(lab)
    h = np.array([s[0].stop - s[0].start for s in sl], float)
    w = np.array([s[1].stop - s[1].start for s in sl], float)

    def mean(x):
        return ndimage.mean(x, lab, idx)

    def mx(x):
        return ndimage.maximum(x, lab, idx)

    def q90(x):
        return np.array([np.quantile(x[lab == i], 0.9) for i in idx]) if n <= 400 else mx(x)

    sev3 = ndimage.sum(pred == 3, lab, idx)
    yy, xx = np.mgrid[: lab.shape[0], : lab.shape[1]]
    cy, cx = mean(yy.astype(float)), mean(xx.astype(float))
    main_area = lab == idx[np.argmax(area)]
    main_sev3 = lab == idx[np.argmax(sev3 + 1e-3 * area)]
    d_area = ndimage.distance_transform_edt(~main_area)
    d_sev3 = ndimage.distance_transform_edt(~main_sev3)
    ring = ndimage.binary_dilation(cand, EIGHT, iterations=5) & ~cand
    ring_lab = ndimage.grey_dilation(lab, footprint=np.ones((11, 11)))
    ring_lab = np.where(ring, ring_lab, 0)
    ring_n = np.maximum(ndimage.sum(np.ones_like(p_burn), ring_lab, idx), 1)
    ring_dnbr = ndimage.sum(dnbr, ring_lab, idx) / ring_n
    border = np.zeros_like(cand)
    border[[0, -1], :] = border[:, [0, -1]] = True
    feats = np.stack(
        [
            np.log1p(area),
            perim / np.sqrt(area),
            4 * np.pi * area / np.maximum(perim, 1) ** 2,
            np.maximum(h, w) / np.maximum(np.minimum(h, w), 1),
            area / (h * w),
            mean(p_burn),
            mx(p_burn),
            q90(p_burn),
            mean(dnbr),
            mx(dnbr),
            q90(dnbr),
            mean(dlow),
            mean((pred == 2).astype(float)),
            sev3 / area,
            mean((org == 2).astype(float)),
            mean((org == 3).astype(float)),
            mean((lc == 2).astype(float)),
            mean((lc == 1).astype(float)),
            mean((lc == 0).astype(float)),
            mean((lc == 3).astype(float)),
            (-area).argsort().argsort() / n,
            (-sev3).argsort().argsort() / n,
            area / area.sum(),
            ndimage.minimum(d_area, lab, idx),
            ndimage.minimum(d_sev3, lab, idx),
            np.full(n, np.log1p(n)),
            np.full(n, cand.mean()),
            np.full(n, np.quantile(dnbr[valid], 0.9)),
            np.hypot(cy - 255.5, cx - 255.5),
            ndimage.maximum(border, lab, idx).astype(float),
            ring_dnbr,
            ndimage.sum(p_burn, ring_lab, idx) / ring_n,
            ndimage.sum((org >= 1).astype(float), ring_lab, idx) / ring_n,
            mean(dnbr) - ring_dnbr,
        ],
        1,
    ).astype(np.float32)
    return lab, feats


def local(x: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray]:
    m = ndimage.uniform_filter(x, size)
    return m, np.sqrt(np.maximum(ndimage.uniform_filter(x * x, size) - m * m, 0))


def comp_pixels(lab: np.ndarray, feats: np.ndarray, names: tuple) -> list[np.ndarray]:
    cols = [COMP_FEATURES.index(n) for n in names]
    table = (
        np.vstack([np.full((1, len(cols)), -1.0, np.float32), feats[:, cols]])
        if len(feats)
        else np.full((1, len(cols)), -1.0, np.float32)
    )
    return [table[lab, i] for i in range(len(cols))]


def chip_features(raw, probs, pred, th) -> tuple[dict, np.ndarray]:
    idx = spectral_indices(raw.refl)
    dnbr = idx["dnbr"]
    tmap = threshold_map(raw.landcover, th)
    org = organizer_severity(dnbr, tmap)
    lc = group_map(raw.landcover, th)
    valid = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
    p_burn = 1.0 - probs[0]
    lab5, f5 = component_table(p_burn, pred, dnbr, dnbr - tmap[0], org, lc, valid)
    lab3, f3 = component_table(p_burn, pred, dnbr, dnbr - tmap[0], org, lc, valid, cand_t=0.3)
    sev3 = ndimage.sum(pred == 3, lab5, np.arange(1, len(f5) + 1)) if len(f5) else np.zeros(0)
    area = (
        ndimage.sum(np.ones_like(dnbr), lab5, np.arange(1, len(f5) + 1)) if len(f5) else np.zeros(0)
    )
    if len(f5):
        main_sev3 = lab5 == 1 + int(np.argmax(sev3 + 1e-3 * area))
        main_area = lab5 == 1 + int(np.argmax(area))
    else:
        main_sev3 = main_area = np.zeros_like(valid)
    dm11, ds11 = local(dnbr, 11)
    dm41, ds41 = local(dnbr, 41)
    org1 = (org >= 1).astype(np.float32)
    same41 = np.zeros_like(dnbr)
    for g in range(4):
        frac = ndimage.uniform_filter((lc == g).astype(np.float32), 41)
        same41 = np.where(lc == g, frac, same41)
    f = {
        "p0": probs[0],
        "p1": probs[1],
        "p2": probs[2],
        "p3": probs[3],
        "p_burn": p_burn,
        "pred": pred,
        "dnbr": dnbr,
        "rdnbr": idx["rdnbr"],
        "d_low": dnbr - tmap[0],
        "d_mod": dnbr - tmap[1],
        "org": org,
        "lc": lc,
        "ndvi_post": idx["ndvi_post"],
        "dndvi": idx["dndvi"],
        "scl_pre": raw.scl_pre,
        "scl_post": raw.scl_post,
        "dnbr_mean11": dm11,
        "dnbr_std11": ds11,
        "dnbr_mean41": dm41,
        "dnbr_std41": ds41,
        "pb_mean11": ndimage.uniform_filter(p_burn, 11),
        "pb_max11": ndimage.maximum_filter(p_burn, 11),
        "pb_mean41": ndimage.uniform_filter(p_burn, 41),
        "pb_max41": ndimage.maximum_filter(p_burn, 41),
        "org1_frac11": ndimage.uniform_filter(org1, 11),
        "org1_frac41": ndimage.uniform_filter(org1, 41),
        "dlow_min11": ndimage.minimum_filter(dnbr - tmap[0], 11),
        "samelc_frac41": same41,
        "dist_boundary": signed_boundary_distance(pred > 0),
        "dist_main_sev3_px": distance_to(main_sev3),
        "dist_main_area_px": distance_to(main_area),
        "dist_core": distance_to(clean_core((p_burn >= 0.8) | (pred >= 2), 20)),
        "chip_burn_frac": np.full(dnbr.shape, (pred > 0).mean(), np.float32),
        "chip_n_comp": np.full(dnbr.shape, np.log1p(len(f5)), np.float32),
        "chip_dnbr_q90": np.full(
            dnbr.shape, np.quantile(dnbr[valid], 0.9) if valid.any() else 0, np.float32
        ),
    }
    for n, v in zip(COMP05, comp_pixels(lab5, f5, COMP05), strict=True):
        f[f"c05_{n}"] = v
    for n, v in zip(COMP03, comp_pixels(lab3, f3, COMP03), strict=True):
        f[f"c03_{n}"] = v
    zone = ((p_burn >= ZONE_P) | (np.abs(f["dist_boundary"]) <= ZONE_R)) & valid
    return f, zone


def hybrid_c(f: dict, w: float) -> np.ndarray:
    burn = f["pred"] > 0
    org = np.clip(f["org_sev"], 1, 3)
    sev_p = np.stack([f["p1"], f["p2"], f["p3"]])
    logp = np.log(np.maximum(sev_p, 1e-8))
    onehot = np.stack([(org == c) for c in (1, 2, 3)]).astype(np.float32)
    return np.where(burn, 1 + (logp + w * onehot).argmax(0), 0)


def v004_test_maps(logits: np.ndarray, f: dict, refiner: lgb.Booster) -> dict:
    probs = softmax(logits)
    wide = refine_gate(f, WIDE["band"], WIDE["radius"], WIDE["keep_conf"])
    sel = np.nonzero(wide.ravel())[0]
    flat = probs.reshape(4, -1).copy()
    if len(sel):
        logp = np.log(np.maximum(refiner.predict(stack(f, wide)), 1e-9)) + V004_BIAS
        p_burn, dist = f["p_burn"].ravel()[sel], f["dist_pred_boundary"].ravel()[sel]
        gate = (p_burn >= BAND) & (p_burn <= 1 - BAND) | (np.abs(dist) <= RADIUS)
        refined = np.exp(logp[gate])
        flat[:, sel[gate]] = (refined / refined.sum(1, keepdims=True)).T
    probs = flat.reshape(probs.shape)
    pred = probs.argmax(0)
    final = hybrid_c({**f, "pred": pred}, 1.0)
    return {"probs": probs, "pred": final}
