import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
from build_submission import validate

REPO = Path(__file__).resolve().parents[2]
SUBMISSIONS = REPO / "artifacts" / "submissions"
PARENT = SUBMISSIONS / "submission_v004.csv"


def build(bs_path: Path, out: Path, manifest_extra: dict) -> dict:
    if out.exists():
        raise FileExistsError(f"{out} already exists; submissions are never overwritten")
    parent = pd.read_csv(PARENT, keep_default_na=False)
    bs = pd.read_csv(bs_path, keep_default_na=False).set_index(["chip_id", "class_id"])["rle"]
    is_bs = parent.chip_id.str.startswith("BS_")
    keys = list(zip(parent.loc[is_bs, "chip_id"], parent.loc[is_bs, "class_id"], strict=True))
    missing = [k for k in keys if k not in bs.index]
    if missing or len(bs) != len(keys):
        raise ValueError(
            f"BS rows mismatch: missing={missing[:5]} new={len(bs)} parent={len(keys)}"
        )
    out_df = parent.copy()
    out_df.loc[is_bs, "rle"] = [bs[k] for k in keys]
    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out, index=False)
    old = PARENT.read_text().splitlines()
    new = out.read_text().splitlines()
    if len(old) != len(new) or old[0] != new[0]:
        raise RuntimeError("header or row count differs from parent")
    af_same = all(a == b for a, b in zip(old, new, strict=True) if not a.startswith("BS_"))
    if not af_same:
        raise RuntimeError("AF rows differ from parent")
    if not new[1].startswith("AF_te_000001,1,"):
        raise RuntimeError("first data row must be AF_te_000001,1")
    validation = validate(out)
    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "submission_path": str(out.relative_to(REPO)),
        "submission_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "parent": "submission_v004.csv (public 0.7406)",
        "rows": {
            "total": len(out_df),
            "af": validation["af_chips"],
            "bs": validation["bs_chips"] * 3,
        },
        "af_byte_identical_to_v004_and_v003": af_same,
        "validation": validation,
        **manifest_extra,
    }
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=float) + "\n")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--bs", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--manifest-json", required=True, type=Path)
    args = p.parse_args()
    extra = json.loads(args.manifest_json.read_text())
    m = build(args.bs.resolve(), args.out.resolve(), extra)
    print(
        json.dumps(
            {
                k: m[k]
                for k in (
                    "submission_path",
                    "submission_sha256",
                    "rows",
                    "af_byte_identical_to_v004_and_v003",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
