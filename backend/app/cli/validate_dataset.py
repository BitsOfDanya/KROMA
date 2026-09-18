from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.repositories.prepared import PreparedDatasetRepository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate KROMA prepared-dataset manifests, checksums and geometries."
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "prepared_data",
        help="manifest.json or a directory containing one or more manifests",
    )
    args = parser.parse_args()
    repository = PreparedDatasetRepository(args.path)
    body = {
        "status": "ok" if repository.list() else "error",
        "datasets": [
            {
                "dataset_id": item.manifest.dataset_id,
                "dataset_version": item.manifest.dataset_version,
                "origin": item.manifest.origin,
                "processing_version": item.manifest.processing_version,
                "fingerprint": item.fingerprint,
                "hotspots": len(item.hotspots),
                "burn_zones": len(item.burn_zones),
            }
            for item in repository.list()
        ],
        "errors": repository.errors,
    }
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0 if repository.list() else 1


if __name__ == "__main__":
    raise SystemExit(main())
