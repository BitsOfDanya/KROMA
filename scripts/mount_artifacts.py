import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ml" / "src"))

from kroma_ml.artifacts import (
    AF_VERSION,
    ARTIFACTS,
    BS_VERSION,
    DEFAULT_ROOT,
    sha256,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dest", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--link", action="store_true", help="symlink instead of copying")
    p.add_argument(
        "--source-manifest", type=Path, default=REPO / "artifacts/submissions/submission_v005.json"
    )
    args = p.parse_args()

    files, missing = {}, []
    for key, (relative, source) in ARTIFACTS.items():
        if not source.is_file():
            missing.append(str(source.relative_to(REPO)))
            continue
        target = args.dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        if args.link:
            target.symlink_to(source.resolve())
        else:
            shutil.copy2(source, target)
        files[key] = {
            "path": relative,
            "bytes": source.stat().st_size,
            "sha256": sha256(source),
            "source": str(source.relative_to(REPO)),
        }
    if missing:
        sys.exit("missing source artifacts:\n  " + "\n  ".join(missing))

    provenance = {}
    if args.source_manifest.is_file():
        m = json.loads(args.source_manifest.read_text())
        provenance = {
            "submission": m.get("submission_path"),
            "public_score": m.get("public_score"),
            "oof_all_valid": m.get("oof_all_valid"),
            "oof_strict": m.get("oof_strict"),
            "oof_iou_all_valid": m.get("oof_iou_all_valid"),
        }
    manifest = {
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "af_model_version": AF_VERSION,
        "bs_model_version": BS_VERSION,
        "provenance": provenance,
        "files": files,
    }
    (args.dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    total = sum(f["bytes"] for f in files.values()) / 1e6
    print(f"mounted {len(files)} artifacts ({total:.1f} MB) -> {args.dest}")


if __name__ == "__main__":
    main()
