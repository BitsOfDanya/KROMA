import json
import os
import subprocess
import sys
import time
from pathlib import Path

from bs_track_report import OUT_JSON, TRACK, collect, row

REPO = Path(__file__).resolve().parents[2]
PARALLEL = int(os.environ.get("KROMA_TRACK_PARALLEL", "3"))
BUSY_PATTERN = os.environ.get("KROMA_TRACK_WAIT_FOR", "bs_train.py")
BASE_MIX = "random:0.5,class1:0.3,burn:0.2"
MARGIN = 0.002


def busy() -> bool:
    out = subprocess.run(["pgrep", "-f", BUSY_PATTERN], capture_output=True, text=True)
    return bool(out.stdout.strip())


def wait_for_compute() -> None:
    while busy():
        print("waiting for active queue to finish", flush=True)
        time.sleep(60)


def launch(run_id: str, extra: list[str]) -> dict:
    logs = TRACK / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    pending = [k for k in (1, 2, 3) if not (TRACK / f"{run_id}_f{k}.json").exists()]
    for start in range(0, len(pending), PARALLEL):
        wait_for_compute()
        procs = []
        for k in pending[start : start + PARALLEL]:
            cmd = [sys.executable, "-u", str(REPO / "research/experiments/bs_track.py"),
                   "--id", run_id, "--fold", str(k), *extra]  # fmt: skip
            log = open(logs / f"{run_id}_f{k}.log", "w")
            procs.append(
                (subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=REPO), log)
            )
        for proc, log in procs:
            proc.wait()
            log.close()
            if proc.returncode:
                raise RuntimeError(f"{run_id} failed, see {log.name}")
    summary = collect([run_id])[run_id]
    r = row(summary)
    print(
        f"DONE {run_id} bs={r['bs_mean']:.4f} worst={r['bs_worst']:.4f} iou1={r['iou1']:.3f}",
        flush=True,
    )
    return summary


def better(cand: dict, inc: dict) -> bool:
    c, i = row(cand), row(inc)
    if c["bs_mean"] > i["bs_mean"] + MARGIN:
        return True
    return c["bs_mean"] >= i["bs_mean"] - MARGIN and c["iou1"] > i["iou1"] * 1.05


def pick(incumbent: tuple[str, dict, list[str]], cands: list[tuple[str, list[str]]]):
    best = incumbent
    for run_id, args in cands:
        summary = launch(run_id, args)
        if better(summary, best[1]):
            best = (run_id, summary, args)
    print(f"STAGE WINNER {best[0]}", flush=True)
    return best


def scale_mix(mix: str, keep: float, add: str) -> str:
    parts = [p.split(":") for p in mix.split(",")]
    return ",".join([f"{k}:{float(v) * keep:.3f}" for k, v in parts] + [add])


def main() -> None:
    decisions = {}
    base = ["--mix", BASE_MIX]
    control = ("c0", launch("c0", base), base)
    best = pick(control, [
        ("s_c1", ["--mix", "random:0.3,class1:0.5,burn:0.2"]),
        ("s_bnd", ["--mix", "random:0.3,class1:0.3,burn:0.1,b01:0.15,b12:0.15"]),
    ])  # fmt: skip
    decisions["sampler"] = best[0]
    mix = best[2][best[2].index("--mix") + 1]
    best = pick(
        best, [("h_mine", ["--mix", scale_mix(mix, 0.75, "hard:0.25"), "--hard-from", "c0"])]
    )
    decisions["hard_mining"] = best[0]
    recipe = best[2]
    best = pick(best, [
        ("l_dice1", [*recipe, "--loss", "ohem_dice1"]),
        ("l_tversky1", [*recipe, "--loss", "ohem_tversky1"]),
        ("l_lovasz", [*recipe, "--loss", "ohem_lovasz"]),
        ("l_w15", [*recipe, "--w1", "1.5"]),
    ])  # fmt: skip
    decisions["loss"] = best[0]
    recipe = best[2]
    best = pick(best, [
        ("p_score", [*recipe, "--extra", "phys_score"]),
        ("p_raw", [*recipe, "--drop-indices"]),
    ])  # fmt: skip
    decisions["features"] = best[0]
    recipe = best[2]
    best = pick(best, [
        ("x_crop384", [*recipe, "--crop", "384", "--batch", "4"]),
        ("x_crop512", [*recipe, "--crop", "512", "--batch", "2"]),
    ])  # fmt: skip
    decisions["context"] = best[0]
    recipe = best[2]
    models = [
        ("m_segformer", [*recipe, "--model", "segformer_b0", "--opt", "adamw", "--lr", "1e-3"]),
        ("m_mobile", [*recipe, "--model", "mobileunet", "--opt", "adamw", "--lr", "1e-3"]),
    ]
    model_runs = {run_id: launch(run_id, args) for run_id, args in models}
    decisions["models"] = {k: row(v) for k, v in model_runs.items()}
    decisions["winner"] = best[0]
    decisions["winner_args"] = best[2]
    launch(
        "c_old", ["--config", "B", "--ohem", "0.25", "--scl-ignore", "strict", "--brightness", "0"]
    )
    existing = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {}
    existing["decisions"] = decisions
    OUT_JSON.write_text(json.dumps(existing, indent=2, default=float) + "\n")
    print(json.dumps(decisions, indent=1, default=float), flush=True)


if __name__ == "__main__":
    main()
