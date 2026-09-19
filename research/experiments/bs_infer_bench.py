import argparse
import io
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
from kroma_ml.bs_crop import CONFIGS
from kroma_ml.bs_fast_models import MODEL_NAMES, build_model
from kroma_ml.bs_physics import spectral_indices, threshold_classes
from kroma_ml.bs_sampling import track_channels

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "research" / "experiments" / "bs_infer_bench.json"
CHANNELS = CONFIGS["B12_lc5"]


def timed(fn, repeats: int, sync) -> float:
    fn()
    sync()
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        sync()
        times.append(time.perf_counter() - t0)
    return 1000 * float(np.median(times))


def bench_one(name: str, dev_name: str, threads: int) -> dict:
    torch.set_num_threads(threads)
    dev = torch.device(dev_name)
    model = build_model(name, len(CHANNELS)).eval().to(dev)
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    sync = torch.mps.synchronize if dev_name == "mps" else (lambda: None)
    out = {
        "model": name,
        "device": dev_name,
        "params": int(sum(p.numel() for p in model.parameters())),
        "size_mb_fp32": round(buf.tell() / 2**20, 2),
    }
    rng = np.random.default_rng(0)
    refl = rng.uniform(0.02, 0.4, (8, 512, 512)).astype(np.float32)
    lc = np.full((512, 512), 40, np.int16)
    scl = np.full((512, 512), 4, np.uint8)
    out["features_ms_scene"] = round(
        timed(lambda: track_channels(refl, lc, scl, scl, CHANNELS), 5, lambda: None), 2
    )
    with torch.no_grad():
        for label, shape in (
            ("crop256_b1_ms", (1, len(CHANNELS), 256, 256)),
            ("scene512_b1_ms", (1, len(CHANNELS), 512, 512)),
            ("scene512_b8_ms_per_scene", (8, len(CHANNELS), 512, 512)),
        ):
            x = torch.randn(*shape, device=dev)
            reps = 3 if shape[0] > 1 else 10
            ms = timed(lambda x=x: model(x), reps, sync)
            out[label] = round(ms / shape[0], 2)
    if dev_name == "mps":
        out["mps_driver_mb"] = round(torch.mps.driver_allocated_memory() / 2**20, 1)
    out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 1)
    return out


def onnx_check(name: str) -> dict:
    model = build_model(name, len(CHANNELS)).eval()
    x = torch.randn(1, len(CHANNELS), 512, 512)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.onnx"
        try:
            torch.onnx.export(model, (x,), str(path), opset_version=17, dynamo=False,
                              input_names=["x"], output_names=["logits"])  # fmt: skip
            return {
                "model": name,
                "onnx_export": "ok",
                "onnx_mb": round(path.stat().st_size / 2**20, 2),
            }
        except Exception as exc:
            return {"model": name, "onnx_export": f"failed: {type(exc).__name__}: {str(exc)[:160]}"}


def physics_latency() -> dict:
    rng = np.random.default_rng(0)
    refl = rng.uniform(0.02, 0.4, (8, 512, 512)).astype(np.float32)
    ms = timed(
        lambda: threshold_classes(spectral_indices(refl)["dnbr"], (0.105, 0.205, 0.39)),
        10,
        lambda: None,
    )
    return {
        "model": "physics_dnbr_thresholds",
        "device": "cpu",
        "scene512_b1_ms": round(ms, 2),
        "params": 3,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--one", nargs=3, metavar=("MODEL", "DEVICE", "THREADS"))
    args = p.parse_args()
    if args.one:
        print(json.dumps(bench_one(args.one[0], args.one[1], int(args.one[2]))))
        return
    rows = [physics_latency()]
    devices = [("cpu", "4")] + ([("mps", "4")] if torch.backends.mps.is_available() else [])
    for name in MODEL_NAMES:
        for dev, threads in devices:
            res = subprocess.run(
                [sys.executable, __file__, "--one", name, dev, threads],
                capture_output=True,
                text=True,
                check=True,
            )
            rows.append(json.loads(res.stdout.strip().splitlines()[-1]))
            print(rows[-1], flush=True)
    onnx = [onnx_check(name) for name in MODEL_NAMES]
    OUT_JSON.write_text(json.dumps({"benchmarks": rows, "onnx": onnx}, indent=2) + "\n")
    print(json.dumps(onnx, indent=1))


if __name__ == "__main__":
    main()
