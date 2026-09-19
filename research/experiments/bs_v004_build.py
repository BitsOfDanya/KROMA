import hashlib
import json
import time
from pathlib import Path

import pandas as pd
from build_submission import SUBMISSIONS, validate

REPO = Path(__file__).resolve().parents[2]
V003 = REPO / SUBMISSIONS / "submission_v003.csv"
V003_MANIFEST = REPO / SUBMISSIONS / "submission_v003.json"
BS_V004 = REPO / "artifacts" / "bs_submission_v004.csv"
BS_V004_MANIFEST = REPO / "artifacts" / "bs_test_manifest_v004.json"
COMBO = REPO / "research" / "experiments" / "bs_v004_combo_results.json"
OUT = REPO / SUBMISSIONS / "submission_v004.csv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"{OUT} already exists; submissions are never overwritten")
    v003 = pd.read_csv(V003, keep_default_na=False)
    bs = pd.read_csv(BS_V004, keep_default_na=False).set_index(["chip_id", "class_id"])["rle"]
    is_bs = v003.chip_id.str.startswith("BS_")
    out = v003.copy()
    keys = list(zip(out.loc[is_bs, "chip_id"], out.loc[is_bs, "class_id"], strict=True))
    missing = [k for k in keys if k not in bs.index]
    if missing or len(bs) != len(keys):
        raise ValueError(f"BS rows mismatch: missing={missing[:5]} v004={len(bs)} v003={len(keys)}")
    out.loc[is_bs, "rle"] = [bs[k] for k in keys]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    af_new = pd.read_csv(OUT, keep_default_na=False)
    af_new = af_new[~af_new.chip_id.str.startswith("BS_")]
    af_old = v003[~is_bs]
    af_identical = af_new.to_csv(index=False).encode() == af_old.to_csv(index=False).encode()
    if not af_identical:
        raise RuntimeError("AF rows differ from v003")
    v003_lines = V003.read_text().splitlines()
    v004_lines = OUT.read_text().splitlines()
    af_line_identical = [
        a == b for a, b in zip(v003_lines, v004_lines, strict=True) if not a.startswith("BS_")
    ]
    validation = validate(OUT)
    combo = json.loads(COMBO.read_text())["variants"]
    best = combo["refiner_band30_r2+hybrid_C_w1.0"]
    base = combo["v003"]
    v003_manifest = json.loads(V003_MANIFEST.read_text())
    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "v004",
        "parent": "v003 (public 0.72)",
        "submission_path": str(OUT.relative_to(REPO)),
        "submission_sha256": validation["sha256"],
        "rows": {"af": validation["af_chips"], "bs": validation["bs_chips"] * 3, "total": len(out)},
        "af": {
            **v003_manifest["af"],
            "byte_identical_to_v003": bool(all(af_line_identical)),
        },
        "bs": {
            "base": "v003 full-train ensemble, reproduced byte-exactly before post-processing",
            "post_processing": [
                "LightGBM refiner on v003 probabilities + organizer landcover dNBR physics, "
                "applied only where 0.3<=p_burn<=0.7 or within 2 px of the predicted contour",
                "hybrid C: burn mask from refined prediction; severity = argmax(log p_sev + "
                "1.0 * onehot(organizer landcover severity))",
            ],
            "organizer_thresholds": "research/experiments/bs_v004_physics_thresholds.json",
            "oof_all_valid_bs": {
                "v003": base["all_valid_mask"]["bs_mean"],
                "v004": best["all_valid_mask"]["bs_mean"],
            },
            "oof_strict_bs": {
                "v003": base["strict_mask"]["bs_mean"],
                "v004": best["strict_mask"]["bs_mean"],
            },
            "oof_per_fold_all_valid": {
                "v003": base["all_valid_mask"]["per_fold"],
                "v004": best["all_valid_mask"]["per_fold"],
            },
            "oof_iou_per_class_all_valid": {
                "v003": base["all_valid_mask"]["pooled"]["iou_per_class"],
                "v004": best["all_valid_mask"]["pooled"]["iou_per_class"],
            },
            "test_inference": json.loads(BS_V004_MANIFEST.read_text()),
        },
        "validation": validation,
        "public_score": None,
    }
    OUT.with_suffix(".json").write_text(json.dumps(manifest, indent=2, default=float) + "\n")
    print(json.dumps({k: manifest[k] for k in ("submission_path", "rows", "validation")}, indent=2))
    print("af byte identical:", manifest["af"]["byte_identical_to_v003"], "sha:", sha(OUT))


if __name__ == "__main__":
    main()
