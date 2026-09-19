import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from kroma_ml.submission import decode_rle, encode_rle, multiclass_to_binary_rles

AF_SHAPE = (256, 256)
BS_SHAPE = (512, 512)


def _init_worker() -> None:
    from kroma_ml import service

    service.af_bundle()
    service.bs_models()


def _af_task(chip_id: str, root: str) -> tuple[str, str, int, str | None]:
    from kroma_ml import service

    try:
        mask = service.predict_af(chip_id, root)["mask"]
        return chip_id, encode_rle(mask), int(mask.sum()), None
    except Exception as error:
        return chip_id, "", 0, f"{type(error).__name__}: {error}"


def _bs_task(chip_id: str, root: str, logits_path: str) -> tuple[str, dict, list[int], str | None]:
    from kroma_ml import service

    try:
        logits = np.load(logits_path)
        mask = service.predict_bs(chip_id, root, logits=logits)["mask"]
        counts = [int((mask == k).sum()) for k in (1, 2, 3)]
        return chip_id, multiclass_to_binary_rles(mask, (1, 2, 3)), counts, None
    except Exception as error:
        empty = encode_rle(np.zeros(BS_SHAPE, dtype=np.uint8))
        return (
            chip_id,
            dict.fromkeys((1, 2, 3), empty),
            [0, 0, 0],
            f"{type(error).__name__}: {error}",
        )


def neural_logits(bs_ids: list[str], root: str, out_dir: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "kroma_ml.bs_neural", "--root", root, "--out-dir", out_dir, *bs_ids],
        check=True,
    )


def validate_frame(frame: pd.DataFrame, template: pd.DataFrame, meta: pd.DataFrame) -> dict:
    if list(frame.columns) != ["chip_id", "class_id", "rle"]:
        raise ValueError("columns must be chip_id,class_id,rle")
    pairs = list(zip(frame.chip_id, frame.class_id, strict=True))
    if pairs != list(zip(template.chip_id, template.class_id, strict=True)):
        raise ValueError("pair set/order differs from the template")
    if len(set(pairs)) != len(pairs) or frame.isna().any().any():
        raise ValueError("duplicate pairs or NaN present")
    kind = meta.set_index("chip_id")["kind"]
    masks: dict[str, list[np.ndarray]] = {}
    for chip_id, class_id, rle in zip(frame.chip_id, frame.class_id, frame.rle, strict=True):
        shape = AF_SHAPE if kind[chip_id] == "af" else BS_SHAPE
        mask = decode_rle(rle, shape)
        if kind[chip_id] == "bs":
            masks.setdefault(chip_id, []).append(mask)
    overlaps = [c for c, m in masks.items() if (np.sum(m, axis=0) > 1).any()]
    if overlaps:
        raise ValueError(f"overlapping BS classes in {len(overlaps)} chips")
    return {"rows": len(frame), "af_chips": int((kind == "af").sum()), "bs_chips": len(masks)}


def run(
    data_dir: Path, output: Path, workers: int, threads: int, template_path: Path | None
) -> dict:
    t_start = time.perf_counter()
    meta = pd.read_csv(data_dir / "meta.csv")
    template = pd.read_csv(
        template_path or data_dir / "sample_submission.csv", keep_default_na=False
    )
    af_ids = meta.loc[meta.kind == "af", "chip_id"].tolist()
    bs_ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()
    af_root, bs_root = str(data_dir / "af"), str(data_dir / "bs")
    stages: dict[str, float] = {}

    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.perf_counter()
        if bs_ids:
            neural_logits(bs_ids, bs_root, tmp)
        stages["bs_neural_incl_model_load_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        os.environ["OMP_NUM_THREADS"] = str(threads)
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(workers, ctx, initializer=_init_worker) as pool:
            stages["worker_start_and_model_load_s"] = time.perf_counter() - t0
            t0 = time.perf_counter()
            af_jobs = [pool.submit(_af_task, cid, af_root) for cid in af_ids]
            bs_jobs = [pool.submit(_bs_task, cid, bs_root, f"{tmp}/{cid}.npy") for cid in bs_ids]
            af_out = [job.result() for job in af_jobs]
            bs_out = [job.result() for job in bs_jobs]
        stages["af_and_bs_postprocess_parallel_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    rles: dict[tuple[str, int], str] = {}
    errors = []
    for chip_id, rle, _, error in af_out:
        rles[(chip_id, 1)] = rle
        errors += [f"{chip_id}: {error}"] if error else []
    for chip_id, by_class, _, error in bs_out:
        for class_id, rle in by_class.items():
            rles[(chip_id, class_id)] = rle
        errors += [f"{chip_id}: {error}"] if error else []
    frame = template[["chip_id", "class_id"]].copy()
    frame["rle"] = [rles[(c, int(k))] for c, k in zip(frame.chip_id, frame.class_id, strict=True)]
    validation = validate_frame(frame, template, meta)
    if errors:
        raise RuntimeError("Inference failed; submission was not written: " + "; ".join(errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    stages["assemble_validate_write_s"] = time.perf_counter() - t0

    return {
        "output": str(output),
        "validation": validation,
        "chips_failed": errors,
        "af_fire_pixels": int(sum(x[2] for x in af_out)),
        "bs_burn_pixels": int(sum(sum(x[2]) for x in bs_out)),
        "workers": workers,
        "threads_per_worker": threads,
        "stages_seconds": {k: round(v, 2) for k, v in stages.items()},
        "total_seconds": round(time.perf_counter() - t_start, 2),
    }


def verify_against(output: Path, reference: Path) -> dict:
    a = pd.read_csv(output, keep_default_na=False)
    b = pd.read_csv(reference, keep_default_na=False)
    same_rows = a.equals(b)
    return {"reference": str(reference), "csv_identical": bool(same_rows)}


def main() -> None:
    p = argparse.ArgumentParser(description="KROMA competition inference -> submission.csv")
    p.add_argument("--data-dir", type=Path, required=True, help="official test directory")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--template", type=Path, default=None, help="default: <data-dir>/sample_submission.csv"
    )
    p.add_argument("--artifacts", type=Path, default=None, help="sets KROMA_ML_ARTIFACTS_PATH")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument(
        "--threads", type=int, default=0, help="LightGBM threads per worker (0: cores/workers)"
    )
    p.add_argument("--profile", type=Path, default=None, help="write the timing report as JSON")
    p.add_argument("--verify-against", type=Path, default=None)
    args = p.parse_args()
    if args.workers < 1 or args.threads < 0:
        p.error("workers must be positive and threads nonnegative")
    if args.artifacts:
        os.environ["KROMA_ML_ARTIFACTS_PATH"] = str(args.artifacts)
    threads = args.threads or max(1, (os.cpu_count() or 1) // args.workers)
    report = run(args.data_dir, args.output, args.workers, threads, args.template)
    if args.verify_against:
        report["verify"] = verify_against(args.output, args.verify_against)
        if not report["verify"]["csv_identical"]:
            raise SystemExit("Submission differs from reference")
    if args.profile:
        args.profile.parent.mkdir(parents=True, exist_ok=True)
        args.profile.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["chips_failed"]:
        sys.exit(f"{len(report['chips_failed'])} chips fell back to empty masks")


if __name__ == "__main__":
    main()
