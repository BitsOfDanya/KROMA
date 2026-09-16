import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.schemas.observations import Coordinates, HotspotObservation

SOURCES = {
    "VIIRS_SNPP_NRT": "N",
    "VIIRS_NOAA20_NRT": "N20",
    "VIIRS_NOAA21_NRT": "N21",
}
REQUIRED_COLUMNS = {
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "confidence",
    "version",
    "daynight",
}


def normalize_row(row: dict[str, str], source: str) -> HotspotObservation:
    acquisition_time = row["acq_time"].strip().zfill(4)
    if len(acquisition_time) != 4 or not acquisition_time.isdigit():
        raise ValueError("acq_time must contain HHMM")

    acquired_at = datetime.strptime(
        f"{row['acq_date']} {acquisition_time}", "%Y-%m-%d %H%M"
    ).replace(tzinfo=UTC)
    location = Coordinates(latitude=float(row["latitude"]), longitude=float(row["longitude"]))
    satellite = row["satellite"].strip()
    if satellite != SOURCES[source]:
        raise ValueError(f"satellite {satellite!r} does not match source {source}")

    identity = "|".join(
        (
            source,
            satellite,
            acquired_at.isoformat(),
            f"{location.latitude:.5f}",
            f"{location.longitude:.5f}",
        )
    )
    observation_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()

    return HotspotObservation(
        observation_id=observation_id,
        source=source,
        satellite=satellite,
        acquired_at=acquired_at,
        location=location,
        brightness_ti4_kelvin=float(row["bright_ti4"]),
        brightness_ti5_kelvin=float(row["bright_ti5"]) if row.get("bright_ti5") else None,
        frp_mw=float(row["frp"]) if row.get("frp") else None,
        scan_km=float(row["scan"]),
        track_km=float(row["track"]),
        source_confidence=row["confidence"].strip().lower(),
        daynight=row["daynight"].strip().upper(),
        source_version=row["version"].strip(),
    )


def normalize_csv(input_path: Path, output_path: Path, source: str) -> int:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input and output paths must differ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    seen: set[str] = set()

    try:
        with input_path.open(encoding="utf-8-sig", newline="") as source_file:
            reader = csv.DictReader(source_file)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"missing FIRMS columns: {', '.join(sorted(missing))}")

            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=output_path.parent, delete=False
            ) as output_file:
                temporary_path = Path(output_file.name)
                for line_number, row in enumerate(reader, start=2):
                    try:
                        observation = normalize_row(row, source)
                    except (
                        AttributeError,
                        KeyError,
                        TypeError,
                        ValueError,
                        ValidationError,
                    ) as error:
                        raise ValueError(f"invalid FIRMS row {line_number}: {error}") from error
                    if observation.observation_id in seen:
                        continue
                    seen.add(observation.observation_id)
                    output_file.write(
                        json.dumps(observation.model_dump(mode="json"), sort_keys=True) + "\n"
                    )

        temporary_path.replace(output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return len(seen)


def fetch_csv(source: str, bounds: list[float], start_date: date, days: int) -> tuple[Path, str]:
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west south east north within valid coordinates")
    if not 1 <= days <= 5:
        raise ValueError("days must be between 1 and 5")

    api_key = os.environ.get("NASA_FIRMS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("NASA_FIRMS_API_KEY is required for download")

    area = ",".join(format(value, "g") for value in bounds)
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{quote(api_key, safe='')}/{source}/{area}/{days}/{start_date.isoformat()}"
    )
    try:
        response = httpx.get(url, headers={"User-Agent": "KROMA/0.1"}, timeout=60)
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise RuntimeError(f"FIRMS request failed with HTTP {error.response.status_code}") from None
    except httpx.RequestError:
        raise RuntimeError("FIRMS request failed due to a network error") from None

    raw_dir = Path("data/raw/firms")
    raw_dir.mkdir(parents=True, exist_ok=True)
    area_id = hashlib.sha256(area.encode("utf-8")).hexdigest()[:12]
    raw_path = raw_dir / f"{source}_{start_date}_{days}_{area_id}.csv"
    raw_path.write_bytes(response.content)
    return raw_path, area


def main() -> None:
    parser = argparse.ArgumentParser(prog="kroma-firms")
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.input is None and (args.bbox is None or args.date is None):
        parser.error("download requires --bbox and --date")

    try:
        input_path, area = (
            (args.input, None)
            if args.input is not None
            else fetch_csv(args.source, args.bbox, args.date, args.days)
        )
        count = normalize_csv(input_path, args.output, args.source)
        manifest = {
            "schema_version": "1.0",
            "source": args.source,
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "observation_count": count,
            "area": area,
            "start_date": args.date.isoformat() if args.date else None,
            "days": args.days if area else None,
        }
        manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    print(f"Wrote {count} observations to {args.output}")


if __name__ == "__main__":
    main()
