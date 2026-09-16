import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from app.services.firms import normalize_csv

SAMPLE_URL = "https://firms.modaps.eosdis.nasa.gov/content/notebooks/sample_viirs_snpp_071223.csv"
SAMPLE_SHA256 = "edf79f62b35ba4485d7c85e01be5f6f61d30ab7b4addcf2eea00e2581982c30f"
SELECTION_SEED = "kroma-viirs-pilot-v1"
RAW_PATH = Path("data/raw/firms/sample_viirs_snpp_071223.csv")
NORMALIZED_PATH = Path("data/interim/sample_viirs_snpp_071223.jsonl")
COHORT_PATH = Path("data/samples/viirs_pilot_cohort.jsonl")


def download_sample() -> None:
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", SAMPLE_URL, timeout=60, follow_redirects=True) as response:
        response.raise_for_status()
        with RAW_PATH.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)


def selection_key(observation_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}|{observation_id}".encode()).hexdigest()


def spatial_split(latitude: float, longitude: float) -> str:
    tile = f"{math.floor(latitude / 5)}:{math.floor(longitude / 5)}"
    bucket = int(hashlib.sha256(tile.encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 6 else "validation" if bucket < 8 else "test"


def build_cohort() -> dict[str, object]:
    raw_hash = hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()
    if raw_hash != SAMPLE_SHA256:
        raise ValueError(f"NASA sample checksum mismatch: {raw_hash}")

    normalized_count = normalize_csv(RAW_PATH, NORMALIZED_PATH, "VIIRS_SNPP_NRT")
    strata: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    with NORMALIZED_PATH.open(encoding="utf-8") as observations:
        for line in observations:
            observation = json.loads(line)
            key = observation["source_confidence"], observation["daynight"]
            strata[key].append(observation)

    selected: list[dict[str, object]] = []
    for key in sorted(strata):
        candidates = sorted(strata[key], key=lambda item: selection_key(item["observation_id"]))
        for observation in candidates[:40]:
            location = observation["location"]
            selected.append(
                {
                    "observation_id": observation["observation_id"],
                    "source": observation["source"],
                    "acquired_at": observation["acquired_at"],
                    "location": location,
                    "source_confidence": observation["source_confidence"],
                    "daynight": observation["daynight"],
                    "split": spatial_split(location["latitude"], location["longitude"]),
                    "reference_label": None,
                }
            )

    selected.sort(key=lambda item: item["observation_id"])
    COHORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(item, sort_keys=True) + "\n" for item in selected)
    COHORT_PATH.write_text(content, encoding="utf-8")

    return {
        "source_url": SAMPLE_URL,
        "source_sha256": raw_hash,
        "source": "VIIRS_SNPP_NRT",
        "selection_seed": SELECTION_SEED,
        "max_per_stratum": 40,
        "normalized_count": normalized_count,
        "selected_count": len(selected),
        "selected_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "strata": dict(sorted((f"{key[0]}_{key[1]}", len(value)) for key, value in strata.items())),
        "selected_splits": dict(sorted(Counter(item["split"] for item in selected).items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="build-evaluation-cohort")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        download_sample()
    if not RAW_PATH.exists():
        parser.error("NASA sample is missing; rerun with --download")
    manifest = build_cohort()
    manifest_path = COHORT_PATH.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {manifest['selected_count']} candidates to {COHORT_PATH}")


if __name__ == "__main__":
    main()
