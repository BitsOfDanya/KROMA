import hashlib
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from bs_v004_fasttrack import THRESHOLDS
from bs_v004_logits import LOGITS_DIR
from bs_v005_components import COMP_DIR, POS_OVERLAP, component_table
from bs_v005_infer import V004_REFINER, v004_test_maps
from bs_v005_refiner2 import CATEGORICAL, FEATURES, R2_DIR, chip_features
from bs_v006_prep import V006
from bs_v006_stack import (
    COMP_PARAMS,
    PIX_PARAMS,
    RE_PIX,
    comp_stats,
    load_comp,
    names_for,
    pixel_rows,
    ring_contrast,
)
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_data import load_chip, load_meta
from kroma_ml.bs_physics import _nd, spectral_indices
from kroma_ml.bs_v004 import (
    group_map,
    load_thresholds,
    organizer_severity,
    pixel_features,
    threshold_map,
)
from kroma_ml.bs_v005 import compose_labels
from kroma_ml.submission import multiclass_to_binary_rles
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "artifacts"
V005_SUB = ARTIFACTS / "submissions" / "submission_v005.csv"
V005_COMP = COMP_DIR / "component_full_v005b_candidate.txt"
V005_R2 = R2_DIR / "refiner2_full_v005b_candidate.txt"
RULE = (0.3, 0.8, 0.2)
SEED = 42
TAG = "v006_rededge"


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


def train_full() -> tuple[lgb.Booster, lgb.Booster]:
    comp_names, pix_names = names_for(["re"])
    ids = load_meta().chip_id.tolist()
    data = [load_comp(c, ["re"]) for c in ids]
    Xc = np.concatenate([d[0] for d in data])
    yc = np.concatenate([(d[1] >= POS_OVERLAP).astype(np.int64) for d in data])
    wc = np.log1p(np.concatenate([d[2] for d in data]))
    bc = lgb.train(COMP_PARAMS, lgb.Dataset(Xc, yc, weight=wc, feature_name=comp_names), 300)
    rng = np.random.default_rng(SEED)
    rows = [pixel_rows(c, ["re"], rng)[:2] for c in ids]
    Xp, yp = np.concatenate([r[0] for r in rows]), np.concatenate([r[1] for r in rows])
    cats = [n for n in CATEGORICAL if n in pix_names]
    bp = lgb.train(
        PIX_PARAMS, lgb.Dataset(Xp, yp, feature_name=pix_names, categorical_feature=cats), 500
    )
    bc.save_model(str(V006 / f"component_full_{TAG}.txt"))
    bp.save_model(str(V006 / f"refiner2_full_{TAG}.txt"))
    return bc, bp


def decide(base, probs, org, lab, cp, zone, r2) -> tuple[np.ndarray, np.ndarray]:
    base_burn = base > 0
    removed = (lab > 0) & (cp < RULE[0])
    burn = (base_burn & ~removed & ~(zone & (r2 < RULE[2]))) | (~removed & zone & (r2 >= RULE[1]))
    return burn, np.where(burn & base_burn, base, compose_labels(burn, probs, org)).astype(np.uint8)


def main() -> None:
    th = load_thresholds(THRESHOLDS)
    refiner = lgb.Booster(model_file=str(V004_REFINER))
    comp5, r2_5 = lgb.Booster(model_file=str(V005_COMP)), lgb.Booster(model_file=str(V005_R2))
    comp6, r2_6 = train_full()
    v005_rows = pd.read_csv(V005_SUB, keep_default_na=False).set_index(["chip_id", "class_id"])[
        "rle"
    ]
    meta = pd.read_csv(REPO / "data/test/meta.csv")
    ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()
    root = str(REPO / "data/test/bs")
    rows, stats, digests, mismatch = [], [], [], []
    started = time.perf_counter()
    for cid in ids:
        raw = load_raw(cid, root=root, with_mask=False)
        logits = np.load(LOGITS_DIR / f"{cid}.npy")
        m = v004_test_maps(logits, pixel_features(raw, logits, th), refiner)
        base, probs = m["pred"].astype(np.int64), m["probs"].astype(np.float32)
        dnbr = spectral_indices(raw.refl)["dnbr"]
        tmap = threshold_map(raw.landcover, th)
        org = organizer_severity(dnbr, tmap)
        lc = group_map(raw.landcover, th)
        valid = ~np.isin(raw.scl_pre, (0, 1)) & ~np.isin(raw.scl_post, (0, 1))
        lab, feats = component_table(1 - probs[0], base, dnbr, dnbr - tmap[0], org, lc, valid)
        f, zone = chip_features(raw, probs, base, th)
        sel = np.nonzero(zone.ravel())[0]
        X = (
            np.stack([np.asarray(f[n], np.float32).ravel()[sel] for n in FEATURES], 1)
            .astype(np.float16)
            .astype(np.float32)
        )
        cp5 = np.concatenate([[1.0], comp5.predict(feats) if len(feats) else []])[lab]
        r5 = np.zeros(base.size, np.float32)
        if len(sel):
            r5[sel] = r2_5.predict(X)
        burn5, lbl5 = decide(base, probs, org, lab, cp5, zone, r5.reshape(base.shape))
        rl5 = multiclass_to_binary_rles(lbl5, (1, 2, 3))
        if any(rl5[k] != v005_rows[(cid, k)] for k in (1, 2, 3)):
            mismatch.append(cid)
        t0 = time.perf_counter()
        re = rededge_maps_root(cid, root)
        re_comp = np.concatenate(
            [comp_stats(lab, [re[k] for k in RE_PIX[:7]]),
             np.stack([ring_contrast(lab, re["dB5"]), ring_contrast(lab, re["dNDRE7"])], 1).reshape(-1, 2)],
            1,
        )  # fmt: skip
        feats6 = (
            np.concatenate([feats, re_comp], 1)
            if len(feats)
            else np.zeros((0, feats.shape[1] + re_comp.shape[1]))
        )
        cp6 = np.concatenate([[1.0], comp6.predict(feats6) if len(feats6) else []])[lab]
        r6 = np.zeros(base.size, np.float32)
        if len(sel):
            re_pix = (
                np.stack([re[k].ravel()[sel] for k in RE_PIX], 1)
                .astype(np.float16)
                .astype(np.float32)
            )
            r6[sel] = r2_6.predict(np.concatenate([X, re_pix], 1))
        burn6, lbl6 = decide(base, probs, org, lab, cp6, zone, r6.reshape(base.shape))
        extra_ms = (time.perf_counter() - t0) * 1000
        rles = multiclass_to_binary_rles(lbl6, (1, 2, 3))
        rows += [(cid, k, rles[k]) for k in (1, 2, 3)]
        digests.append(hashlib.sha256(lbl6.tobytes()).hexdigest())
        stats.append({
            "chip_id": cid, "extra_ms": extra_ms,
            "removed_vs_v005": int((burn5 & ~burn6).sum()), "added_vs_v005": int((~burn5 & burn6).sum()),
            "v005_burn": int(burn5.sum()), "components": int(lab.max()),
            **{f"sev{k}_px": int((lbl6 == k).sum()) for k in (1, 2, 3)},
            **{f"v005_sev{k}_px": int((lbl5 == k).sum()) for k in (1, 2, 3)},
        })  # fmt: skip
    if mismatch:
        raise RuntimeError(f"v005 reconstruction differs for {mismatch[:5]}")
    out = ARTIFACTS / f"bs_submission_{TAG}.csv"
    pd.DataFrame(rows, columns=["chip_id", "class_id", "rle"]).to_csv(out, index=False)
    s = pd.DataFrame(stats)
    manifest = {
        "base": "v005 BS (reproduced byte-exactly on all 89 test chips in the same run)",
        "change": "component classifier and pixel refiner v2 retrained on all 224 train chips with red-edge features (B5/B6/B7 deltas, NDRE5/6/7 deltas, NDRE7 post, local means, component ring contrast); same decision rule 0.3/0.8/0.2",
        "models": [
            str((V006 / f"component_full_{TAG}.txt").relative_to(REPO)),
            str((V006 / f"refiner2_full_{TAG}.txt").relative_to(REPO)),
        ],
        "test_shift_vs_v005": {
            "burn_removed_share": float(s.removed_vs_v005.sum() / s.v005_burn.sum()),
            "burn_added_share": float(s.added_vs_v005.sum() / s.v005_burn.sum()),
            "severity_px": {k: int(s[f"sev{k}_px"].sum()) for k in (1, 2, 3)},
            "v005_severity_px": {k: int(s[f"v005_sev{k}_px"].sum()) for k in (1, 2, 3)},
            "components_total": int(s.components.sum()),
        },
        "extra_ms_per_chip_rededge_stage": round(float(s.extra_ms.mean()), 1),
        "total_seconds": round(time.perf_counter() - started, 1),
        "deterministic_sha256": hashlib.sha256("".join(digests).encode()).hexdigest(),
        "submission": str(out.relative_to(REPO)),
    }
    (ARTIFACTS / f"bs_test_manifest_{TAG}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
