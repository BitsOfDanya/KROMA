import argparse
import json
import shutil
from pathlib import Path

from kroma_ml.artifacts import DEFAULT_ROOT, sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--dest", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    manifest_path = args.source / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for key, item in manifest["files"].items():
        source = args.source / item["path"]
        if not source.is_file() or sha256(source) != item["sha256"]:
            raise SystemExit(f"Missing or corrupt artifact: {key} ({item['path']})")
    if args.source.resolve() != args.dest.resolve():
        for item in manifest["files"].values():
            target = args.dest / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.source / item["path"], target)
        shutil.copy2(manifest_path, args.dest / "manifest.json")
    print(f"Verified {manifest['version']}: {len(manifest['files'])} artifacts")


if __name__ == "__main__":
    main()
