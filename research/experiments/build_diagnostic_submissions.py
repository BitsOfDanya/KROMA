import json
from pathlib import Path

import numpy as np
import pandas as pd
from kroma_ml.submission import roundtrip_check

TEST_ROOT = Path("data/test")
ARTIFACTS = Path("artifacts")
DIAG_DIR = ARTIFACTS / "submissions" / "diagnostic"


def empty_rows(chip_ids: list[str], class_ids: tuple[int, ...], shape: tuple[int, int]) -> list:
    empty_rle = roundtrip_check(np.zeros(shape, dtype=np.uint8))
    return [(cid, class_id, empty_rle) for cid in chip_ids for class_id in class_ids]


def build() -> dict:
    sample = pd.read_csv(TEST_ROOT / "sample_submission.csv", keep_default_na=False)
    test_meta = pd.read_csv(TEST_ROOT / "meta.csv")
    af = pd.read_csv(ARTIFACTS / "af_submission.csv", keep_default_na=False)
    bs = pd.read_csv(ARTIFACTS / "bs_submission.csv", keep_default_na=False)

    af_ids = test_meta.loc[test_meta.kind == "af", "chip_id"].tolist()
    bs_ids = test_meta.loc[test_meta.kind == "bs", "chip_id"].tolist()

    columns = ["chip_id", "class_id", "rle"]
    empty_af = pd.DataFrame(empty_rows(af_ids, (1,), (256, 256)), columns=columns)
    empty_bs = pd.DataFrame(empty_rows(bs_ids, (1, 2, 3), (512, 512)), columns=columns)

    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for name, af_part, bs_part in (
        ("diagnostic_af_only", af, empty_bs),
        ("diagnostic_bs_only", empty_af, bs),
    ):
        combined = pd.concat([af_part, bs_part], ignore_index=True)
        combined = combined.set_index(["chip_id", "class_id"])
        pairs = list(zip(sample.chip_id, sample.class_id, strict=True))
        ordered = combined.loc[pairs].reset_index()[["chip_id", "class_id", "rle"]]
        if len(ordered) != len(sample):
            raise ValueError(f"{name}: row count mismatch")
        path = DIAG_DIR / f"{name}.csv"
        ordered.to_csv(path, index=False)
        outputs[name] = str(path)

    manifest = {
        "note": "diagnostic only, NOT to be uploaded automatically; user decides",
        "diagnostic_af_only": "AF = v001 predictions, BS = all-empty masks",
        "diagnostic_bs_only": "AF = all-empty masks, BS = v001 predictions",
        "paths": outputs,
    }
    (DIAG_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
