import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
from kroma_ml.submission import decode_rle

TEST_ROOT = Path("data/test")
ARTIFACTS = Path("artifacts")
SUBMISSIONS = ARTIFACTS / "submissions"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def assemble(
    version: str,
    af_path: Path = ARTIFACTS / "af_submission.csv",
    bs_path: Path = ARTIFACTS / "bs_submission.csv",
) -> Path:
    sample = pd.read_csv(TEST_ROOT / "sample_submission.csv", keep_default_na=False)
    af = pd.read_csv(af_path, keep_default_na=False)
    bs = pd.read_csv(bs_path, keep_default_na=False)

    combined = pd.concat([af, bs], ignore_index=True)
    combined = combined.set_index(["chip_id", "class_id"])
    template_pairs = list(zip(sample.chip_id, sample.class_id, strict=True))
    missing = [pair for pair in template_pairs if pair not in combined.index]
    if missing:
        shown = missing[:5]
        suffix = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
        raise ValueError(f"missing predictions for pairs: {shown}{suffix}")
    ordered = combined.loc[template_pairs].reset_index()
    ordered = ordered[["chip_id", "class_id", "rle"]]

    SUBMISSIONS.mkdir(parents=True, exist_ok=True)
    out_path = SUBMISSIONS / f"submission_{version}.csv"
    if out_path.exists():
        raise FileExistsError(f"{out_path} already exists; submissions are never overwritten")
    ordered.to_csv(out_path, index=False)
    return out_path


def validate(path: Path) -> dict:
    sample = pd.read_csv(TEST_ROOT / "sample_submission.csv", keep_default_na=False)
    test_meta = pd.read_csv(TEST_ROOT / "meta.csv")
    rows = pd.read_csv(path, keep_default_na=False)

    if list(rows.columns) != ["chip_id", "class_id", "rle"]:
        raise ValueError("columns must be chip_id,class_id,rle")
    if len(rows) != len(sample):
        raise ValueError(f"row count {len(rows)} != template {len(sample)}")
    pairs = list(zip(rows.chip_id, rows.class_id, strict=True))
    if len(set(pairs)) != len(pairs):
        raise ValueError("duplicate (chip_id, class_id) pairs")
    template_pairs = list(zip(sample.chip_id, sample.class_id, strict=True))
    if pairs != template_pairs:
        raise ValueError("row order or pair set differs from template")
    if rows.isna().any().any():
        raise ValueError("NaN present in submission")

    dims = test_meta.set_index("chip_id")[["width", "height"]]
    kinds = test_meta.set_index("chip_id")["kind"]
    decoded_by_chip: dict[str, dict[int, object]] = {}
    for chip_id, class_id, rle in zip(rows.chip_id, rows.class_id, rows.rle, strict=True):
        width, height = int(dims.loc[chip_id, "width"]), int(dims.loc[chip_id, "height"])
        mask = decode_rle(rle, (height, width))
        if 255 in mask:
            raise ValueError(f"decoded mask for {chip_id}/{class_id} leaks value 255")
        decoded_by_chip.setdefault(chip_id, {})[class_id] = mask
        if kinds.loc[chip_id] == "af" and class_id != 1:
            raise ValueError(f"AF chip {chip_id} has unexpected class_id {class_id}")

    overlap_violations = 0
    for chip_id, kind in kinds.items():
        if kind != "bs":
            continue
        masks = decoded_by_chip.get(chip_id, {})
        if set(masks) != {1, 2, 3}:
            raise ValueError(f"BS chip {chip_id} missing one of class_id 1,2,3")
        total = masks[1].astype(int) + masks[2].astype(int) + masks[3].astype(int)
        if (total > 1).any():
            overlap_violations += 1

    if overlap_violations:
        raise ValueError(f"{overlap_violations} BS chips have overlapping severity classes")

    return {
        "path": str(path),
        "rows": len(rows),
        "sha256": _sha256(path),
        "af_chips": int((kinds == "af").sum()),
        "bs_chips": int((kinds == "bs").sum()),
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def write_manifest(
    version: str,
    submission_path: Path,
    validation: dict,
    bs_manifest_path: Path = ARTIFACTS / "bs_test_manifest.json",
    bs_results_path: Path = Path("research/experiments/bs_baseline_results.json"),
    extra_bs_fields: dict | None = None,
) -> Path:
    af_manifest = _load_json(ARTIFACTS / "af_test_manifest.json")
    bs_manifest = _load_json(bs_manifest_path)
    bs_baseline = _load_json(bs_results_path)
    af_calibration = _load_json(Path("research/experiments/af_oof_calibration.json"))

    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": version,
        "submission_path": str(submission_path),
        "submission_sha256": validation["sha256"],
        "rows": {"af": validation["af_chips"], "bs": validation["bs_chips"] * 3},
        "af": {
            "model": af_manifest.get("model"),
            "model_sha256": af_manifest.get("model_sha256"),
            "threshold": af_manifest.get("threshold"),
            "oof_precision": af_calibration.get("oof_precision"),
            "oof_recall": af_calibration.get("oof_recall"),
            "oof_f1": af_calibration.get("oof_f1"),
        },
        "bs": {
            "model": str(bs_manifest.get("model")),
            "config": bs_baseline.get("config"),
            "iou_burn": bs_baseline.get("iou_burn"),
            "miou_severity": bs_baseline.get("miou_severity"),
            "bs_score": bs_baseline.get("bs_score"),
            **(extra_bs_fields or {}),
        },
        "public_score": None,
        "public_f1_af": None,
        "public_iou_burn": None,
        "public_miou_severity": None,
    }
    manifest_path = submission_path.with_suffix(".json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--af-path", default=str(ARTIFACTS / "af_submission.csv"))
    parser.add_argument("--bs-path", default=str(ARTIFACTS / "bs_submission.csv"))
    parser.add_argument("--bs-manifest", default=str(ARTIFACTS / "bs_test_manifest.json"))
    parser.add_argument("--bs-results", default="research/experiments/bs_baseline_results.json")
    parser.add_argument("--bs-note", default="")
    args = parser.parse_args()
    path = assemble(args.version, af_path=Path(args.af_path), bs_path=Path(args.bs_path))
    validation = validate(path)
    extra = {"note": args.bs_note} if args.bs_note else None
    manifest_path = write_manifest(
        args.version,
        path,
        validation,
        bs_manifest_path=Path(args.bs_manifest),
        bs_results_path=Path(args.bs_results),
        extra_bs_fields=extra,
    )
    print(json.dumps({"validation": validation, "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()
