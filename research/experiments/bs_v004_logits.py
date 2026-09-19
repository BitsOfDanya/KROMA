from pathlib import Path

import numpy as np
import pandas as pd
from kroma_ml.bs_crop import load_raw
from kroma_ml.bs_v004 import V003_BIAS
from kroma_ml.submission import multiclass_to_binary_rles

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data" / "processed" / "bs_v004"
V003_MEMBERS = (
    REPO / "research/experiments/bs_full_ndvi_ohem40.pt",
    REPO / "research/experiments/bs_full_dual.pt",
)
V003_BS = REPO / "artifacts" / "bs_submission_v003.csv"
LOGITS_DIR = OUT_DIR / "test_logits"


def dump_logits(ids: list[str]) -> None:
    from bs_test_infer_ensemble import load_member, member_logits

    members = [load_member(str(m)) for m in V003_MEMBERS]
    v003_rows = pd.read_csv(V003_BS, keep_default_na=False).set_index(["chip_id", "class_id"])[
        "rle"
    ]
    LOGITS_DIR.mkdir(parents=True, exist_ok=True)
    mismatch = []
    for cid in ids:
        raw = load_raw(cid, root=str(REPO / "data/test/bs"), with_mask=False)
        logits = sum(member_logits(m, c, raw) for m, c in members) / len(members)
        logits = (logits + V003_BIAS[:, None, None]).astype(np.float32)
        rles = multiclass_to_binary_rles(logits.argmax(0).astype(np.uint8), (1, 2, 3))
        if any(rles[k] != v003_rows[(cid, k)] for k in (1, 2, 3)):
            mismatch.append(cid)
        np.save(LOGITS_DIR / f"{cid}.npy", logits)
    if mismatch:
        raise RuntimeError(f"v003 reconstruction differs from submission for {mismatch[:5]}")
    print(f"v003 reproduced byte-exactly for {len(ids)} chips", flush=True)


def main() -> None:
    meta = pd.read_csv(REPO / "data/test/meta.csv")
    dump_logits(meta.loc[meta.kind == "bs", "chip_id"].tolist())


if __name__ == "__main__":
    main()
