import argparse
import glob
import json
import struct
import zlib
from pathlib import Path

import numpy as np
from kroma_ml.bs_crop import LC_GROUPS, load_raw
from kroma_ml.bs_cv import MASK_MODES, confusion, fold_of, load_predictions, valid_mask
from kroma_ml.bs_data import SCL_INVALID_STRICT, load_meta
from kroma_ml.bs_metrics import NUM_CLASSES
from kroma_ml.bs_physics import (
    INDEX_NAMES,
    USGS_DNBR,
    Hist1D,
    class_stats,
    pairwise_separability,
    spectral_indices,
)
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_class1_audit.json"
MONTAGE_DIR = REPO / "data" / "processed" / "bs_class1"
RANGES = {
    "nbr_pre": (-1.0, 1.0),
    "nbr_post": (-1.0, 1.0),
    "dnbr": (-1.5, 1.5),
    "rdnbr": (-6.0, 6.0),
    "rdnbr_b11": (-6.0, 6.0),
    "ndvi_pre": (-1.0, 1.0),
    "ndvi_post": (-1.0, 1.0),
    "dndvi": (-1.5, 1.5),
    "d_nir": (-0.5, 0.5),
    "d_swir1": (-0.5, 0.5),
    "d_swir2": (-0.5, 0.5),
}
BINS = 600
EIGHT = np.ones((3, 3), dtype=bool)
SMALL_COMPONENT = 9
NOISE_TYPES = (
    "c1_unburned_dnbr_lt_0.10",
    "c1_greening_dnbr_lt_0",
    "c3_unburned_dnbr_lt_0.10",
    "c0_burnlike_dnbr_gt_0.27",
    "c0_burnlike_within_3px_of_burn",
    "c0_burnlike_far_from_burn",
    "severity_jump_ge2",
    "c1_tiny_component_le9px",
    "c1_within_2px_of_cloud_shadow",
    "c1_inside_strict_invalid",
)
LC_ORDER = (*LC_GROUPS, "lc_other")


def lc_group(landcover: np.ndarray) -> np.ndarray:
    out = np.full(landcover.shape, len(LC_GROUPS), dtype=np.int64)
    for i, codes in enumerate(LC_GROUPS.values()):
        out[np.isin(landcover, codes)] = i
    return out


def neighbour_classes(mask: np.ndarray) -> np.ndarray:
    present = np.zeros((NUM_CLASSES, *mask.shape), dtype=bool)
    for c in range(NUM_CLASSES):
        present[c] = ndimage.binary_dilation(mask == c, EIGHT)
    return present


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    a = (a - a.mean()) * np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]
    b = (b - b.mean()) * np.hanning(b.shape[0])[:, None] * np.hanning(b.shape[1])[None, :]
    fa, fb = np.fft.fft2(a), np.fft.fft2(b)
    r = fa * np.conj(fb)
    corr = np.fft.fftshift(np.real(np.fft.ifft2(r / (np.abs(r) + 1e-12))))
    cy, cx = np.unravel_index(int(np.argmax(corr)), corr.shape)
    out = []
    for axis, c in ((0, cy), (1, cx)):
        idx = [cy, cx]
        vals = []
        for d in (-1, 0, 1):
            idx[axis] = (c + d) % corr.shape[axis]
            vals.append(corr[idx[0], idx[1]])
        den = vals[0] - 2 * vals[1] + vals[2]
        sub = 0.5 * (vals[0] - vals[2]) / den if abs(den) > 1e-12 else 0.0
        out.append(c - corr.shape[axis] // 2 + sub)
    return float(out[0]), float(out[1])


def mask_shift(burn: np.ndarray, dnbr: np.ndarray, valid: np.ndarray, r: int = 3) -> tuple:
    if burn[valid].mean() < 0.01 or burn[valid].mean() > 0.99:
        return None
    x = np.where(valid, dnbr, 0.0)
    best, arg = -np.inf, (0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            shifted = np.roll(np.roll(burn, dy, 0), dx, 1)
            m = valid & np.roll(np.roll(valid, dy, 0), dx, 1)
            v = x[m & shifted].mean() - x[m & ~shifted].mean()
            if v > best:
                best, arg = v, (dy, dx)
    return arg


def component_areas(binary: np.ndarray) -> np.ndarray:
    lab, n = ndimage.label(binary, EIGHT)
    return np.bincount(lab.ravel())[1:] if n else np.zeros(0, dtype=np.int64)


def quantiles(values: np.ndarray) -> dict:
    if len(values) == 0:
        return {"n": 0}
    p25, p50, p75 = np.percentile(values, [25, 50, 75])
    return {
        "n": int(len(values)),
        "p25": float(p25),
        "median": float(p50),
        "p75": float(p75),
        "mean": float(values.mean()),
    }


def hist_quant(counts: np.ndarray, edges: np.ndarray) -> dict:
    n = counts.sum()
    if n == 0:
        return {"n": 0}
    cdf = np.cumsum(counts) / n
    return {
        "n": int(n),
        **{f"p{p}": round(float(np.interp(p / 100, cdf, edges[1:])), 4) for p in (25, 50, 75)},
    }


def png(path: Path, rgb: np.ndarray) -> None:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def stretch(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((x - lo) / (hi - lo) * 255, 0, 255)


PALETTE = np.array([[30, 30, 30], [255, 220, 0], [255, 120, 0], [200, 0, 0]], dtype=np.float64)


def montage_tile(raw, idx: dict, candidate: np.ndarray) -> np.ndarray:
    post = np.stack([raw.refl[7], raw.refl[5], raw.refl[4]], -1)
    fc = stretch(post, 0.0, 0.35)
    dn = stretch(idx["dnbr"], -0.3, 0.8)
    dnbr_rgb = np.stack([dn, dn, dn], -1)
    gt = PALETTE[raw.mask]
    over = gt.copy()
    over[candidate] = [0, 200, 255]
    sep = np.full((raw.mask.shape[0], 6, 3), 255.0)
    return np.concatenate([fc, sep, dnbr_rgb, sep, gt, sep, over], 1)


def audit(max_chips: int | None) -> dict:
    meta = load_meta()
    folds = fold_of(meta)
    ids = meta["chip_id"].tolist()[:max_chips]
    splits = ("fold1", "fold2", "fold3", "all")
    per_split = {
        s: {
            "px": np.zeros(NUM_CLASSES, dtype=np.int64),
            "scenes": 0,
            "scenes_c1": 0,
            "c1_areas": [],
            "c1_nb": np.zeros(NUM_CLASSES, dtype=np.int64),
            "c1_boundary": 0,
        }
        for s in splits
    }
    hists = {n: Hist1D.empty(*RANGES[n], BINS) for n in INDEX_NAMES}
    lc_dnbr = {g: Hist1D.empty(-1.5, 1.5, BINS) for g in LC_ORDER}
    scl = {m: {"removed": np.zeros(NUM_CLASSES, dtype=np.int64)} for m in MASK_MODES}
    total_px = np.zeros(NUM_CLASSES, dtype=np.int64)
    c1_removed_pre = np.zeros(256, dtype=np.int64)
    c1_removed_post = np.zeros(256, dtype=np.int64)
    c1_removed_scene = []
    c1_valid_vs_removed = {k: Hist1D.empty(-1.5, 1.5, BINS) for k in ("kept", "removed")}
    noise = {
        t: {"count": 0, "areas": [], "dnbr": np.zeros(BINS, dtype=np.int64)} for t in NOISE_TYPES
    }
    dnbr_edges = np.linspace(-1.5, 1.5, BINS + 1)
    per_scene_noise = []
    shifts_prepost, shifts_mask = [], []
    for n_done, chip_id in enumerate(ids):
        raw = load_raw(chip_id)
        mask = raw.mask.astype(np.int64)
        idx = spectral_indices(raw.refl)
        valid_true = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
        valid_strict = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "strict")
        counts = np.bincount(mask.ravel(), minlength=NUM_CLASSES)
        total_px += counts
        c1 = mask == 1
        nb = neighbour_classes(mask)
        c1_areas = component_areas(c1)
        for s in (f"fold{folds[chip_id]}", "all"):
            d = per_split[s]
            d["px"] += counts
            d["scenes"] += 1
            d["scenes_c1"] += int(counts[1] > 0)
            d["c1_areas"].extend(c1_areas.tolist())
            for c in (0, 2, 3):
                d["c1_nb"][c] += int((c1 & nb[c]).sum())
            d["c1_boundary"] += int((c1 & (nb[0] | nb[2] | nb[3])).sum())

        for mode in MASK_MODES:
            v = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, mode)
            scl[mode]["removed"] += np.bincount(mask[~v], minlength=NUM_CLASSES)
        strict_bad = ~valid_strict
        removed1 = c1 & strict_bad
        post_bad = np.isin(raw.scl_post, list(SCL_INVALID_STRICT))
        pre_bad = np.isin(raw.scl_pre, list(SCL_INVALID_STRICT))
        c1_removed_post += np.bincount(raw.scl_post[removed1 & post_bad], minlength=256)
        c1_removed_pre += np.bincount(raw.scl_pre[removed1 & pre_bad & ~post_bad], minlength=256)
        c1_removed_scene.append((chip_id, int(c1.sum()), int(removed1.sum())))
        for key, sel in (("kept", c1 & valid_strict), ("removed", removed1)):
            c1_valid_vs_removed[key].add(idx["dnbr"][sel], np.zeros(int(sel.sum()), dtype=np.int64))

        lab = mask[valid_true]
        for name in INDEX_NAMES:
            hists[name].add(idx[name][valid_true], lab)
        groups = lc_group(raw.landcover)[valid_true]
        dn = idx["dnbr"][valid_true]
        for gi, g in enumerate(LC_ORDER):
            sel = groups == gi
            lc_dnbr[g].add(dn[sel], lab[sel])

        burn = mask > 0
        near_burn = ndimage.binary_dilation(burn, EIGHT, iterations=3)
        near_cloud = ndimage.binary_dilation(strict_bad, EIGHT, iterations=2)
        jump = (nb[0] & nb[2]) | (nb[0] & nb[3]) | (nb[1] & nb[3])
        jump = jump & ((mask == 0) | (mask == 3) | ((mask == 2) & nb[0]) | ((mask == 1) & nb[3]))
        tiny_lab, _ = ndimage.label(c1, EIGHT)
        tiny = np.isin(tiny_lab, np.nonzero(np.bincount(tiny_lab.ravel()) <= SMALL_COMPONENT)[0])
        tiny &= c1
        dnbr = idx["dnbr"]
        burnlike0 = (mask == 0) & (dnbr > USGS_DNBR[1])
        cand = {
            "c1_unburned_dnbr_lt_0.10": c1 & (dnbr < USGS_DNBR[0]),
            "c1_greening_dnbr_lt_0": c1 & (dnbr < 0),
            "c3_unburned_dnbr_lt_0.10": (mask == 3) & (dnbr < USGS_DNBR[0]),
            "c0_burnlike_dnbr_gt_0.27": burnlike0,
            "c0_burnlike_within_3px_of_burn": burnlike0 & near_burn,
            "c0_burnlike_far_from_burn": burnlike0 & ~near_burn,
            "severity_jump_ge2": jump,
            "c1_tiny_component_le9px": tiny,
            "c1_within_2px_of_cloud_shadow": c1 & near_cloud & valid_strict,
            "c1_inside_strict_invalid": c1 & strict_bad,
        }
        scene_row = {"chip_id": chip_id, "c1": int(c1.sum())}
        for t, m in cand.items():
            m = m & valid_true
            noise[t]["count"] += int(m.sum())
            noise[t]["areas"].extend(component_areas(m).tolist())
            b = np.clip(np.searchsorted(dnbr_edges, dnbr[m], side="right") - 1, 0, BINS - 1)
            noise[t]["dnbr"] += np.bincount(b, minlength=BINS)
            scene_row[t] = int(m.sum())
        per_scene_noise.append(scene_row)

        nir_pre = np.where(valid_strict, raw.refl[1], np.median(raw.refl[1]))
        nir_post = np.where(valid_strict, raw.refl[5], np.median(raw.refl[5]))
        if valid_strict.mean() > 0.5:
            shifts_prepost.append((chip_id, *phase_shift(nir_pre, nir_post)))
            ms = mask_shift(burn, dnbr, valid_true)
            if ms is not None:
                shifts_mask.append((chip_id, *ms))
        if (n_done + 1) % 25 == 0:
            print(f"audited {n_done + 1}/{len(ids)}", flush=True)

    result: dict = {"chips": len(ids)}
    split_out = {}
    for s, d in per_split.items():
        areas = np.asarray(d["c1_areas"])
        c1_px = int(d["px"][1])
        split_out[s] = {
            "scenes": d["scenes"],
            "pixels": d["px"].tolist(),
            "percent": (100 * d["px"] / max(d["px"].sum(), 1)).round(3).tolist(),
            "scenes_with_class1": d["scenes_c1"],
            "class1_components": int(len(areas)),
            "class1_component_area_px": quantiles(areas),
            "class1_components_le9px_share": float((areas <= SMALL_COMPONENT).mean())
            if len(areas)
            else 0.0,
            "class1_px_in_le9px_components_share": float(
                areas[areas <= SMALL_COMPONENT].sum() / max(areas.sum(), 1)
            ),
            "class1_px_touching_0": float(d["c1_nb"][0] / max(c1_px, 1)),
            "class1_px_touching_2": float(d["c1_nb"][2] / max(c1_px, 1)),
            "class1_px_touching_3": float(d["c1_nb"][3] / max(c1_px, 1)),
            "class1_px_on_any_boundary": float(d["c1_boundary"] / max(c1_px, 1)),
        }
    result["class_stats_by_split"] = split_out

    scene_loss = np.array([r / max(t, 1) for _, t, r in c1_removed_scene])
    lost = np.array([r for _, _, r in c1_removed_scene])
    order = np.argsort(-lost)
    scl_out = {
        m: {
            "removed_px": scl[m]["removed"].tolist(),
            "removed_share": (scl[m]["removed"] / np.maximum(total_px, 1)).round(4).tolist(),
        }
        for m in MASK_MODES
    }
    scl_out["class1_strict_removed_by_post_scl"] = {
        str(k): int(v) for k, v in enumerate(c1_removed_post) if v
    }
    scl_out["class1_strict_removed_by_pre_scl_only"] = {
        str(k): int(v) for k, v in enumerate(c1_removed_pre) if v
    }
    has_c1 = np.array([t > 0 for _, t, _ in c1_removed_scene])
    scl_out["class1_scene_loss"] = {
        "scenes_with_class1": int(has_c1.sum()),
        "scenes_losing_gt_50pct": int((scene_loss[has_c1] > 0.5).sum()),
        "scenes_losing_gt_90pct": int((scene_loss[has_c1] > 0.9).sum()),
        "top10_scenes_share_of_lost_class1": float(lost[order[:10]].sum() / max(lost.sum(), 1)),
        "top10": [c1_removed_scene[i] for i in order[:10]],
    }
    scl_out["class1_dnbr_kept_vs_removed"] = {
        k: class_stats(h)[0] for k, h in c1_valid_vs_removed.items()
    }
    result["scl_audit"] = scl_out

    result["physical_distributions_all_valid"] = {
        name: {
            "per_class": class_stats(h),
            "sep_0_vs_1": pairwise_separability(h, 0, 1),
            "sep_1_vs_2": pairwise_separability(h, 1, 2),
            "sep_1_vs_3": pairwise_separability(h, 1, 3),
            "sep_2_vs_3": pairwise_separability(h, 2, 3),
        }
        for name, h in hists.items()
    }
    result["dnbr_by_landcover"] = {
        g: {
            "per_class_median": [s.get("p50") for s in class_stats(h)],
            "per_class_n": [s.get("n") for s in class_stats(h)],
            "sep_0_vs_1": pairwise_separability(h, 0, 1),
        }
        for g, h in lc_dnbr.items()
    }
    c1_total = int(sum(h for h in hists["dnbr"].counts[1]))
    result["label_noise_candidates"] = {
        t: {
            "count": v["count"],
            "share_of_class1": round(v["count"] / max(c1_total, 1), 4),
            "mean_component_size_px": round(float(np.mean(v["areas"])), 2) if v["areas"] else 0.0,
            "dnbr": hist_quant(v["dnbr"], dnbr_edges),
        }
        for t, v in noise.items()
    }
    pp = np.array([s[1:] for s in shifts_prepost])
    mk = np.array([s[1:] for s in shifts_mask])
    result["alignment"] = {
        "pre_post_phase_corr": {
            "n": len(pp),
            "abs_dy_median": float(np.median(np.abs(pp[:, 0]))),
            "abs_dx_median": float(np.median(np.abs(pp[:, 1]))),
            "share_gt_0.5px": float((np.hypot(pp[:, 0], pp[:, 1]) > 0.5).mean()),
            "share_gt_1px": float((np.hypot(pp[:, 0], pp[:, 1]) > 1.0).mean()),
            "mean_dy_dx": pp.mean(0).round(3).tolist(),
            "worst": sorted(shifts_prepost, key=lambda s: -np.hypot(s[1], s[2]))[:5],
        },
        "mask_vs_dnbr_integer_shift": {
            "n": len(mk),
            "share_zero_shift": float(((mk[:, 0] == 0) & (mk[:, 1] == 0)).mean()),
            "share_ge2px": float((np.abs(mk).max(1) >= 2).mean()),
            "mean_dy_dx": mk.mean(0).round(3).tolist(),
            "nonzero": [s for s in shifts_mask if s[1] or s[2]][:20],
        },
    }
    result["per_scene_noise_top"] = sorted(
        per_scene_noise, key=lambda r: -r["c1_unburned_dnbr_lt_0.10"]
    )[:10]
    return result


def write_montage(rows: list[dict], k: int = 4) -> list[str]:
    MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for kind in ("c1_unburned_dnbr_lt_0.10", "c0_burnlike_far_from_burn"):
        top = sorted(rows, key=lambda r: -r[kind])[:k]
        tiles = []
        for r in top:
            raw = load_raw(r["chip_id"])
            idx = spectral_indices(raw.refl)
            if kind.startswith("c1"):
                cand = (raw.mask == 1) & (idx["dnbr"] < USGS_DNBR[0])
            else:
                cand = (raw.mask == 0) & (idx["dnbr"] > USGS_DNBR[1])
            tiles.append(montage_tile(raw, idx, cand)[::2, ::2])
            tiles.append(np.full((6, tiles[-1].shape[1], 3), 255.0))
        path = MONTAGE_DIR / f"{kind}.png"
        png(path, np.concatenate(tiles, 0))
        written.append(str(path.relative_to(REPO)))
    return written


def oof_confusion(patterns: list[str]) -> dict:
    meta = load_meta()
    folds = fold_of(meta)
    out = {}
    for pattern in patterns:
        files = sorted(glob.glob(pattern))
        if not files:
            continue
        cm = {m: np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64) for m in ("strict", "true")}
        by_size = {b: np.zeros((NUM_CLASSES,), dtype=np.int64) for b in ("le9", "10_99", "ge100")}
        by_pos = {b: np.zeros((NUM_CLASSES,), dtype=np.int64) for b in ("boundary", "interior")}
        by_lc = {g: np.zeros((NUM_CLASSES,), dtype=np.int64) for g in LC_ORDER}
        by_dnbr = {
            b: np.zeros((NUM_CLASSES,), dtype=np.int64) for b in ("lt0.1", "0.1_0.27", "ge0.27")
        }
        chips, fold_set = 0, set()
        for f in files:
            ids, labels = load_predictions(Path(f))
            for cid, pred in zip(ids, labels, strict=True):
                raw = load_raw(cid)
                fold_set.add(folds[cid])
                chips += 1
                mask = raw.mask.astype(np.int64)
                for m in cm:
                    cm[m] += confusion(
                        pred, mask, valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m)
                    )
                v = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
                c1 = (mask == 1) & v
                lab, _ = ndimage.label(mask == 1, EIGHT)
                area = np.bincount(lab.ravel())[lab]
                nb = neighbour_classes(mask)
                edge = nb[0] | nb[2] | nb[3]
                dnbr = spectral_indices(raw.refl)["dnbr"]
                groups = lc_group(raw.landcover)
                for key, sel in (
                    ("le9", area <= 9),
                    ("10_99", (area > 9) & (area < 100)),
                    ("ge100", area >= 100),
                ):
                    by_size[key] += np.bincount(pred[c1 & sel], minlength=NUM_CLASSES)
                by_pos["boundary"] += np.bincount(pred[c1 & edge], minlength=NUM_CLASSES)
                by_pos["interior"] += np.bincount(pred[c1 & ~edge], minlength=NUM_CLASSES)
                for gi, g in enumerate(LC_ORDER):
                    by_lc[g] += np.bincount(pred[c1 & (groups == gi)], minlength=NUM_CLASSES)
                for key, sel in (
                    ("lt0.1", dnbr < 0.1),
                    ("0.1_0.27", (dnbr >= 0.1) & (dnbr < 0.27)),
                    ("ge0.27", dnbr >= 0.27),
                ):
                    by_dnbr[key] += np.bincount(pred[c1 & sel], minlength=NUM_CLASSES)

        def share(v: np.ndarray) -> dict:
            return {"n": int(v.sum()), "pred_share": (v / max(v.sum(), 1)).round(4).tolist()}

        entry = {"files": files, "chips": chips, "folds": sorted(fold_set)}
        for m, c in cm.items():
            rn = c / np.maximum(c.sum(1, keepdims=True), 1)
            entry[m] = {
                "confusion": c.tolist(),
                "0to1": float(rn[0, 1]),
                "1to0": float(rn[1, 0]),
                "1to1": float(rn[1, 1]),
                "1to2": float(rn[1, 2]),
                "1to3": float(rn[1, 3]),
                "2to1": float(rn[2, 1]),
                "3to1": float(rn[3, 1]),
                "fp1_from_0_share": float(c[0, 1] / max(c[:, 1].sum() - c[1, 1], 1)),
            }
        entry["class1_true_valid_by_component_size"] = {k: share(v) for k, v in by_size.items()}
        entry["class1_true_valid_by_position"] = {k: share(v) for k, v in by_pos.items()}
        entry["class1_true_valid_by_landcover"] = {k: share(v) for k, v in by_lc.items()}
        entry["class1_true_valid_by_dnbr"] = {k: share(v) for k, v in by_dnbr.items()}
        out[pattern] = entry
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--max-chips", type=int, default=None)
    p.add_argument("--oof", nargs="*", default=[])
    p.add_argument("--oof-only", action="store_true")
    args = p.parse_args()
    result = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() and args.oof_only else {}
    if not args.oof_only:
        result = audit(args.max_chips)
        result["montages"] = write_montage(result["per_scene_noise_top"])
    if args.oof:
        result.setdefault("oof_confusion", {}).update(oof_confusion(args.oof))
    OUT_JSON.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "per_scene_noise_top"}, indent=1, default=float
        )[:6000]
    )


if __name__ == "__main__":
    main()
