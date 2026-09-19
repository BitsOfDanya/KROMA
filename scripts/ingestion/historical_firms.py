import argparse
import csv
import hashlib
import json
import math
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.firms import fetch_csv, normalize_csv
from kroma_geo.context import RegionIndex, geometry_bboxes, in_aoi

SOURCES = (
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
    "MODIS_SP",
    "MODIS_NRT",
)


def _cache_path(
    source: str, bbox: tuple[float, float, float, float], start: date, days: int
) -> Path:
    area = ",".join(format(value, "g") for value in bbox)
    area_id = hashlib.sha256(area.encode()).hexdigest()[:12]
    return Path("data/raw/firms") / f"{source}_{start}_{days}_{area_id}.csv"


def _tiles(
    bbox: tuple[float, float, float, float], tile_degrees: float
) -> list[tuple[float, float, float, float]]:
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west south east north")
    if tile_degrees <= 0:
        raise ValueError("tile_degrees must be positive")
    columns = math.ceil((east - west) / tile_degrees)
    rows = math.ceil((north - south) / tile_degrees)
    return [
        (
            west + x * tile_degrees,
            south + y * tile_degrees,
            min(east, west + (x + 1) * tile_degrees),
            min(north, south + (y + 1) * tile_degrees),
        )
        for x in range(columns)
        for y in range(rows)
    ]


def _normalized_rows(path: Path, source: str) -> Iterator[dict[str, Any]]:
    if source.startswith("VIIRS"):
        normalizer_source = source.replace("_SP", "_NRT")
        with tempfile.TemporaryDirectory() as directory:
            normalized = Path(directory) / "observations.jsonl"
            normalize_csv(path, normalized, normalizer_source)
            with normalized.open(encoding="utf-8") as file:
                for line in file:
                    row = json.loads(line)
                    row["source"] = source
                    row["instrument"] = "VIIRS"
                    if source.endswith("_SP"):
                        row["observation_id"] = hashlib.sha256(
                            f"{source}|{row['observation_id']}".encode()
                        ).hexdigest()
                    yield row
        return
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            satellite = row["satellite"].strip().upper()
            if satellite not in {"T", "A"}:
                raise ValueError(f"unexpected MODIS satellite: {satellite}")
            acquired_at = datetime.strptime(
                f"{row['acq_date']} {row['acq_time'].zfill(4)}", "%Y-%m-%d %H%M"
            ).replace(tzinfo=UTC)
            longitude = float(row["longitude"])
            latitude = float(row["latitude"])
            observation_source = (
                f"MODIS_{'TERRA' if satellite == 'T' else 'AQUA'}_{source.split('_')[-1]}"
            )
            identity = (
                f"{observation_source}|{acquired_at.isoformat()}|{latitude:.5f}|{longitude:.5f}"
            )
            yield {
                "schema_version": "research-1.1",
                "observation_id": hashlib.sha256(identity.encode()).hexdigest(),
                "source": observation_source,
                "satellite": satellite,
                "instrument": "MODIS",
                "acquired_at": acquired_at.isoformat(),
                "location": {"latitude": latitude, "longitude": longitude},
                "brightness_ti4_kelvin": None,
                "brightness_modis_kelvin": float(row["brightness"]),
                "brightness_t31_kelvin": float(row["bright_t31"])
                if row.get("bright_t31")
                else None,
                "frp_mw": float(row["frp"]) if row.get("frp") else None,
                "scan_km": float(row["scan"]),
                "track_km": float(row["track"]),
                "source_confidence": int(row["confidence"]),
                "daynight": row["daynight"].strip().upper(),
                "source_version": row["version"],
            }


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.date_from > args.date_to:
        raise ValueError("date_from must be <= date_to")
    if args.region_code and not args.regions:
        raise ValueError("region_code requires regions GeoJSON")
    region_index = RegionIndex.from_geojson(args.regions) if args.regions else None
    region = region_index.by_code[args.region_code] if args.region_code else None
    aoi_data = json.loads(args.aoi.read_text()) if args.aoi else None
    geometry = aoi_data.get("geometry", aoi_data) if aoi_data else None
    if region and geometry:
        raise ValueError("choose region_code or aoi GeoJSON")
    geometry = region.geometry if region else geometry
    boxes = (tuple(args.bbox),) if args.bbox else geometry_bboxes(geometry) if geometry else ()
    if not boxes:
        raise ValueError("bbox, region_code, or aoi is required")
    tiles = sorted({tile for box in boxes for tile in _tiles(box, args.tile_degrees)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    chunks = []
    output_hash = hashlib.sha256()
    observation_count = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as output:
            temporary_path = Path(output.name)
            for source in args.sources:
                start = args.date_from
                while start <= args.date_to:
                    days = min(5, (args.date_to - start).days + 1)
                    seen: set[str] = set()
                    for tile in tiles:
                        raw = _cache_path(source, tile, start, days)
                        cached = raw.exists()
                        if not cached:
                            raw, _ = fetch_csv(source, list(tile), start, days)
                        accepted = 0
                        for row in _normalized_rows(raw, source):
                            location = row["location"]
                            acquired = date.fromisoformat(str(row["acquired_at"])[:10])
                            if not start <= acquired < start + timedelta(days=days):
                                continue
                            if not in_aoi(
                                location["longitude"],
                                location["latitude"],
                                tuple(args.bbox) if args.bbox else None,
                                geometry,
                            ):
                                continue
                            if row["observation_id"] in seen:
                                continue
                            seen.add(row["observation_id"])
                            encoded = json.dumps(row, sort_keys=True) + "\n"
                            output.write(encoded)
                            output_hash.update(encoded.encode())
                            observation_count += 1
                            accepted += 1
                        chunks.append(
                            {
                                "source": source,
                                "bbox": tile,
                                "start_date": start.isoformat(),
                                "days": days,
                                "raw_path": str(raw),
                                "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                                "cached": cached,
                                "accepted_count": accepted,
                            }
                        )
                    start += timedelta(days=days)
        temporary_path.replace(args.output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    manifest = {
        "processing_version": "research-1.2",
        "created_at": datetime.now(UTC).isoformat(),
        "aoi": {
            "bboxes": boxes,
            "region": args.region_code,
            "geojson": str(args.aoi) if args.aoi else None,
        },
        "date_from": args.date_from.isoformat(),
        "date_to": args.date_to.isoformat(),
        "historical_from": args.date_from.isoformat(),
        "historical_to": args.date_to.isoformat(),
        "sources": args.sources,
        "number_of_observations": observation_count,
        "output_sha256": output_hash.hexdigest(),
        "chunks": chunks,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="historical-firms")
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    parser.add_argument("--aoi", type=Path)
    parser.add_argument("--regions", type=Path)
    parser.add_argument("--region-code")
    parser.add_argument("--date-from", type=date.fromisoformat, required=True)
    parser.add_argument("--date-to", type=date.fromisoformat, required=True)
    parser.add_argument("--source", action="append", dest="sources", choices=SOURCES, required=True)
    parser.add_argument("--tile-degrees", type=float, default=10.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = run(args)
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(f"Wrote {manifest['number_of_observations']} observations to {args.output}")


if __name__ == "__main__":
    main()
