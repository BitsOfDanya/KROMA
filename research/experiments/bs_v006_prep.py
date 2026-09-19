import argparse
import json
from pathlib import Path

import numpy as np
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_data import load_meta

REPO = Path(__file__).resolve().parents[2]
V006 = REPO / "data" / "processed" / "bs_v006"
V005_OOF = V006 / "oof_v005"
CTX_DIR = V006 / "ctx_single_split"
V004_DIR = REPO / "data" / "processed" / "bs_v005" / "oof_v004"
COMP_DIR = REPO / "data" / "processed" / "bs_v005" / "components"
R2_DIR = REPO / "data" / "processed" / "bs_v005" / "refiner2"
COMP_T, ADD_T, RM_T = 0.3, 0.8, 0.2


def v005_decision(cid: str) -> dict:
    with np.load(V004_DIR / f"{cid}.npz") as z:
        pred, probs, k = z["pred"].astype(np.int64), z["probs"].astype(np.float32), int(z["fold"])
    lab = np.load(COMP_DIR / f"{cid}.npz")["lab"]
    cp = np.load(COMP_DIR / f"{cid}_prob.npy").astype(np.float32)
    sel = np.load(R2_DIR / f"{cid}_sel.npy")
    r2 = np.zeros(pred.size, np.float32)
    r2[sel] = np.load(R2_DIR / f"{cid}_p.npy").astype(np.float32)
    zone = np.zeros(pred.size, bool)
    zone[sel] = True
    r2, zone = r2.reshape(pred.shape), zone.reshape(pred.shape)
    base = pred > 0
    removed = (lab > 0) & (cp < COMP_T)
    burn = (base & ~removed & ~(zone & (r2 < RM_T))) | (~removed & zone & (r2 >= ADD_T))
    return {"pred4": pred, "probs": probs, "fold": k, "lab": lab, "cp": cp, "r2": r2, "zone": zone, "burn": burn}


def materialize_v005() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from bs_v004_fasttrack import THRESHOLDS
    from bs_v005_contour_diag import CROP, GRASS, Tally
    from kroma_ml.bs_cv import EVAL_MODES, valid_mask
    from kroma_ml.bs_physics import spectral_indices
    from kroma_ml.bs_v004 import group_map, load_thresholds, organizer_severity, threshold_map
    from kroma_ml.bs_v005 import compose_labels

    th = load_thresholds(THRESHOLDS)
    V005_OOF.mkdir(parents=True, exist_ok=True)
    tally = Tally()
    for cid in load_meta().chip_id:
        d = v005_decision(cid)
        raw = load_raw(cid)
        dnbr = spectral_indices(raw.refl)["dnbr"]
        org = organizer_severity(dnbr, threshold_map(raw.landcover, th))
        label = np.where(d["burn"] & (d["pred4"] > 0), d["pred4"], compose_labels(d["burn"], d["probs"], org))
        lc = group_map(raw.landcover, th)
        valids = {n: valid_mask(raw.scl_pre, raw.scl_post, raw.refl, m) for n, m in EVAL_MODES.items()}
        va = valids["all_valid_mask"]
        masks = {**valids, "crop": va & (lc == CROP), "grass": va & (lc == GRASS)}
        tally.add("v005", d["fold"], label, raw.mask.astype(np.int64), masks)
        np.savez(V005_OOF / f"{cid}.npz", label=label.astype(np.uint8), burn=d["burn"], fold=np.int8(d["fold"]))
    e = tally.summary()["v005"]
    print(json.dumps({"all_valid": e["all_valid_mask"]["bs_mean"], "strict": e["strict_mask"]["bs_mean"]}))


def ctx_inference(names: list[str]) -> None:
    import torch
    from bs_test_infer_ensemble import load_member, member_logits
    from kroma_ml.af_split import train_val_split

    _, val_ids = train_val_split(load_meta())
    for name in names:
        out = CTX_DIR / name
        out.mkdir(parents=True, exist_ok=True)
        ckpt_path = REPO / "research" / "experiments" / f"bs_exp_{name}.pt"
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        ckpt.setdefault("channel_names", ckpt["channel_names"])
        model, meta = load_member(str(ckpt_path))
        for cid in val_ids:
            logits = member_logits(model, meta, load_raw(cid))
            z = logits - logits.max(0, keepdims=True)
            p = np.exp(z)
            np.save(out / f"{cid}.npy", (p / p.sum(0, keepdims=True)).astype(np.float16))
        print(f"{name}: {len(val_ids)} val chips", flush=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", required=True, choices=("v005", "ctx"))
    p.add_argument("--ctx", nargs="*", default=["ctx512", "ctx384"])
    args = p.parse_args()
    if args.stage == "v005":
        materialize_v005()
    else:
        ctx_inference(args.ctx)


if __name__ == "__main__":
    main()
