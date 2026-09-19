import argparse
import json
import time
from pathlib import Path

import numpy as np
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_cv import (
    EVAL_MODES,
    N_FOLDS,
    confusion,
    evaluate_scenes,
    fold_of,
    summarize_folds,
    valid_mask,
)
from kroma_ml.bs_data import load_meta
from kroma_ml.bs_metrics import NUM_CLASSES
from kroma_ml.bs_physics import (
    MILLER_THODE_RDNBR,
    USGS_DNBR,
    Hist1D,
    Hist2D,
    fit_gated,
    fit_thresholds_1d,
    gated_classes,
    spectral_indices,
    threshold_classes,
)

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_physics_baseline_results.json"
OOF_DIR = REPO / "data" / "processed" / "bs_oof"
H1 = {"dnbr": (-0.5, 1.5, 400), "rdnbr": (-2.0, 6.0, 400), "rdnbr_b11": (-2.0, 6.0, 400)}
H2 = {
    "dnbr_x_rdnbr": ("dnbr", (-0.5, 1.5, 160), "rdnbr", (-2.0, 6.0, 160)),
    "dndvi_x_dnbr": ("dndvi", (-0.5, 1.5, 160), "dnbr", (-0.5, 1.5, 160)),
    "rdnbr_x_dnbr": ("rdnbr", (-2.0, 6.0, 160), "dnbr", (-0.5, 1.5, 160)),
}
FIXED = {"usgs_dnbr": ("dnbr", USGS_DNBR), "miller_thode_rdnbr": ("rdnbr", MILLER_THODE_RDNBR)}
FITTED_1D = {"fit_dnbr": "dnbr", "fit_rdnbr": "rdnbr", "fit_rdnbr_b11_legacy": "rdnbr_b11"}
FITTED_2D = {
    "fit_dnbr_gate_rdnbr_sev": "dnbr_x_rdnbr",
    "fit_rdnbr_gate_dnbr_sev": "rdnbr_x_dnbr",
    "fit_dndvi_gate_dnbr_sev": "dndvi_x_dnbr",
}
VARIANTS = (*FIXED, *FITTED_1D, *FITTED_2D)


def empty_hists() -> dict:
    h = {k: Hist1D.empty(*v) for k, v in H1.items()}
    h.update({k: Hist2D.empty(v[1], v[3]) for k, v in H2.items()})
    return h


def add_chip(hists: dict, idx: dict, mask: np.ndarray, valid: np.ndarray) -> None:
    lab = mask[valid]
    for k in H1:
        hists[k].add(idx[k][valid], lab)
    for k, (a, _, b, _) in H2.items():
        hists[k].add(idx[a][valid], idx[b][valid], lab)


def merged(parts: list[dict]) -> dict:
    out = empty_hists()
    for part in parts:
        for k in out:
            out[k].counts += part[k].counts
    return out


def fit_all(hists: dict) -> dict:
    params = {}
    for name, key in FITTED_1D.items():
        t, s = fit_thresholds_1d(hists[key])
        params[name] = {"index": key, "thresholds": t, "train_bs": s}
    for name, key in FITTED_2D.items():
        t, s = fit_gated(hists[key])
        gate, sev = H2[key][0], H2[key][2]
        params[name] = {"gate": gate, "severity": sev, "thresholds": t, "train_bs": s}
    for name, (key, t) in FIXED.items():
        params[name] = {"index": key, "thresholds": t, "train_bs": None}
    return params


def predict(params: dict, idx: dict) -> np.ndarray:
    if "gate" in params:
        t = params["thresholds"]
        return gated_classes(idx[params["gate"]], t[0], idx[params["severity"]], (t[1], t[2]))
    return threshold_classes(idx[params["index"]], params["thresholds"])


def run(max_chips: int | None) -> dict:
    meta = load_meta()
    folds = fold_of(meta)
    ids = meta["chip_id"].tolist()[:max_chips]
    started = time.perf_counter()
    by_fold = {m: {k: empty_hists() for k in range(1, N_FOLDS + 1)} for m in EVAL_MODES}
    for chip_id in ids:
        raw = load_raw(chip_id)
        idx = spectral_indices(raw.refl)
        mask = raw.mask.astype(np.int64)
        for m, mode in EVAL_MODES.items():
            valid = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, mode)
            add_chip(by_fold[m][folds[chip_id]], idx, mask, valid)
    hist_seconds = time.perf_counter() - started

    params = {m: {} for m in EVAL_MODES}
    for m in EVAL_MODES:
        for k in range(1, N_FOLDS + 1):
            train = merged([by_fold[m][j] for j in by_fold[m] if j != k])
            params[m][k] = fit_all(train)
        params[m]["full_train"] = fit_all(merged(list(by_fold[m].values())))

    result = {
        "chips": len(ids),
        "fit_protocol": "thresholds fitted on the 2 training folds (GroupKFold, fire_event_id)",
        "hist_seconds": round(hist_seconds, 1),
        "variants": {v: {m: {"per_fold": {}} for m in EVAL_MODES} for v in VARIANTS},
    }
    pooled = {
        m: {v: np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64) for v in VARIANTS}
        for m in EVAL_MODES
    }
    latency = []
    OOF_DIR.mkdir(parents=True, exist_ok=True)
    for k in range(1, N_FOLDS + 1):
        fold_chips = [c for c in ids if folds[c] == k]
        if not fold_chips:
            continue
        preds = {m: {v: [] for v in VARIANTS} for m in EVAL_MODES}
        valids = {m: [] for m in EVAL_MODES}
        trues = []
        for chip_id in fold_chips:
            raw = load_raw(chip_id)
            t0 = time.perf_counter()
            idx = spectral_indices(raw.refl)
            predict(params["all_valid_mask"][k]["fit_dnbr_gate_rdnbr_sev"], idx)
            latency.append(time.perf_counter() - t0)
            trues.append(raw.mask.astype(np.uint8))
            for m, mode in EVAL_MODES.items():
                valids[m].append(valid_mask(raw.scl_pre, raw.scl_post, raw.refl, mode))
                for v in VARIANTS:
                    preds[m][v].append(predict(params[m][k][v], idx).astype(np.uint8))
        for m in EVAL_MODES:
            for v in VARIANTS:
                per_fold = result["variants"][v][m]["per_fold"]
                per_fold[k] = evaluate_scenes(preds[m][v], trues, valids[m])
                for p_, t_, v_ in zip(preds[m][v], trues, valids[m], strict=True):
                    pooled[m][v] += confusion(p_, t_, v_)
        for v in VARIANTS:
            np.savez_compressed(
                OOF_DIR / f"physics_{v}_f{k}.npz",
                ids=np.asarray(fold_chips),
                labels=np.stack(preds["all_valid_mask"][v]),
            )
    result["latency_ms_per_scene_cpu"] = round(1000 * float(np.median(latency)), 2)
    for v in VARIANTS:
        for m in EVAL_MODES:
            per_fold = result["variants"][v][m].pop("per_fold")
            entry = summarize_folds(per_fold, pooled[m][v])
            entry["params_per_fold"] = {str(k): params[m][k][v] for k in per_fold}
            entry["params_full_train"] = params[m]["full_train"][v]
            result["variants"][v][m] = entry
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--max-chips", type=int, default=None)
    args = p.parse_args()
    result = run(args.max_chips)
    OUT_JSON.write_text(json.dumps(result, indent=2, default=float) + "\n")
    for v, entry in result["variants"].items():
        for m, e in entry.items():
            s, pooled = e["summary"], e["pooled"]
            print(
                f"{v:28s} {m:15s} bs={s['bs_score']['mean']:.4f}±{s['bs_score']['std']:.4f} "
                f"pooled={pooled['bs_score']:.4f} burn={pooled['iou_burn']:.3f} "
                f"iou={[round(x, 3) for x in pooled['iou_per_class']]} "
                f"P1={pooled['precision_per_class'][1]:.3f} R1={pooled['recall_per_class'][1]:.3f}"
            )


if __name__ == "__main__":
    main()
