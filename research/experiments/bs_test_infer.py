import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from kroma_ml.bs_data import load_chip
from kroma_ml.bs_model import BSPredictor
from kroma_ml.submission import multiclass_to_binary_rles

TEST_ROOT = Path("data/test/bs")
ARTIFACTS = Path("artifacts")


def run(
    model_path: str = "research/experiments/bs_baseline_model.pt",
    class_bias: list[float] | None = None,
    tag: str = "",
) -> dict:
    test_meta = pd.read_csv("data/test/meta.csv")
    bs_ids = test_meta.loc[test_meta.kind == "bs", "chip_id"].tolist()
    bias = np.array(class_bias, dtype=np.float32) if class_bias else None
    predictor = BSPredictor(model_path, device="cpu", class_bias=bias)

    ARTIFACTS.mkdir(exist_ok=True)
    suffix = f"_{tag}" if tag else ""
    submission_path = ARTIFACTS / f"bs_submission{suffix}.csv"
    rows = []
    chip_stats = []
    started = time.perf_counter()
    for cid in bs_ids:
        chip = load_chip(cid, root=str(TEST_ROOT), with_mask=False)
        t0 = time.perf_counter()
        pred = predictor.predict_chip(chip)
        runtime_ms = (time.perf_counter() - t0) * 1000
        rles = multiclass_to_binary_rles(pred, (1, 2, 3))
        for class_id in (1, 2, 3):
            rows.append((cid, class_id, rles[class_id]))
        chip_stats.append(
            {
                "chip_id": cid,
                "sev1_px": int((pred == 1).sum()),
                "sev2_px": int((pred == 2).sum()),
                "sev3_px": int((pred == 3).sum()),
                "runtime_ms": runtime_ms,
            }
        )
    total_seconds = time.perf_counter() - started

    frame = pd.DataFrame(rows, columns=["chip_id", "class_id", "rle"])
    frame.to_csv(submission_path, index=False)
    chips = pd.DataFrame(chip_stats)
    chips.to_csv(ARTIFACTS / f"bs_test_chips{suffix}.csv", index=False)

    result = {
        "model": model_path,
        "class_bias": class_bias,
        "bs_chips": len(bs_ids),
        "total_seconds": round(total_seconds, 2),
        "mean_ms_per_chip": round(float(chips.runtime_ms.mean()), 3),
        "total_sev1_px": int(chips.sev1_px.sum()),
        "total_sev2_px": int(chips.sev2_px.sum()),
        "total_sev3_px": int(chips.sev3_px.sum()),
        "chips_with_any_burn": int(((chips.sev1_px + chips.sev2_px + chips.sev3_px) > 0).sum()),
        "submission": str(submission_path),
    }
    (ARTIFACTS / f"bs_test_manifest{suffix}.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="research/experiments/bs_baseline_model.pt")
    parser.add_argument("--bias", default="")
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    bias = [float(x) for x in args.bias.split(",")] if args.bias else None
    print(json.dumps(run(model_path=args.model, class_bias=bias, tag=args.tag), indent=2))


if __name__ == "__main__":
    main()
