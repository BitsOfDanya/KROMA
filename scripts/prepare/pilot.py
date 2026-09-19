import argparse
import hashlib
import json
import time
import tracemalloc
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from kroma_geo.context import RegionIndex, in_aoi, nearest_context
from kroma_ml.features import incident_features
from kroma_ml.incidents import Observation, cluster_incidents
from kroma_ml.thermal_memory import EqualAreaGrid, ThermalMemory

CONTEXT_CATEGORIES = (
    "settlement",
    "road",
    "power_line",
    "industrial",
    "airport",
    "railway",
    "protected_area",
)


def _context_source(settings: dict[str, object] | None) -> tuple[list[dict], str | None]:
    if not settings:
        return [], None
    path = Path(str(settings["path"]))
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    if checksum != settings["sha256"]:
        raise ValueError("context SHA-256 does not match pilot config")
    collection = json.loads(content)
    if collection.get("type") != "FeatureCollection":
        raise ValueError("context file must be a GeoJSON FeatureCollection")
    return collection["features"], checksum


def _incident_context(
    longitude: float,
    latitude: float,
    settings: dict[str, object] | None,
    features: list[dict],
) -> tuple[dict[str, object], dict[str, object]]:
    if not settings:
        return {"status": "unavailable"}, {}
    if not in_aoi(longitude, latitude, tuple(settings["bbox"])):
        return {"status": "outside_coverage"}, {}
    nearest = nearest_context((longitude, latitude), features, CONTEXT_CATEGORIES)
    compact = {
        category: (
            {"name": item["name"], "distance_km": item["distance_km"]}
            if item
            else None
        )
        for category, item in nearest.items()
    }
    flattened = {
        f"distance_to_{category}_km": item["distance_km"] if item else None
        for category, item in nearest.items()
        if category != "protected_area"
    }
    flattened["protected_area_intersection"] = (
        True
        if nearest["protected_area"] and nearest["protected_area"]["distance_km"] == 0
        else None
    )
    return {"status": "partial_coverage", "nearest": compact}, flattened


def _load(
    path: Path,
    regions: RegionIndex | None,
    bboxes: list[tuple[float, float, float, float]],
    sources: set[str],
) -> list[Observation]:
    observations = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            location = record["location"]
            if record["source"] not in sources or not any(
                in_aoi(location["longitude"], location["latitude"], bbox) for bbox in bboxes
            ):
                continue
            region = (
                regions.assign(location["longitude"], location["latitude"]) if regions else None
            )
            observations.append(Observation.from_record(record, region.code if region else None))
    return observations


def _select(
    observations: list[Observation],
    bbox: tuple[float, float, float, float],
    start: date,
    end: date,
    sources: set[str],
    region_code: str | None,
) -> list[Observation]:
    return [
        item
        for item in observations
        if start <= item.acquired_at.date() <= end
        and item.source in sources
        and in_aoi(item.longitude, item.latitude, bbox)
        and (region_code is None or item.region == region_code)
    ]


def run(
    input_path: Path,
    config_path: Path,
    output_dir: Path,
    manifest_path: Path,
    history_path: Path | None = None,
    regions_path: Path | None = None,
) -> dict[str, object]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if any(pilot.get("region_code") for pilot in config["pilots"]) and not regions_path:
        raise ValueError("region_code pilots require --regions GeoJSON")
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if config.get("input_sha256") and input_sha256 != config["input_sha256"]:
        raise ValueError("input SHA-256 does not match pilot config")
    region_sha256 = hashlib.sha256(regions_path.read_bytes()).hexdigest() if regions_path else None
    if config.get("region_sha256") and region_sha256 != config["region_sha256"]:
        raise ValueError("region SHA-256 does not match pilot config")
    regions = RegionIndex.from_geojson(regions_path) if regions_path else None
    if regions:
        unknown = {pilot.get("region_code") for pilot in config["pilots"]} - {
            None,
            *regions.by_code,
        }
        if unknown:
            raise ValueError(f"unknown region codes: {', '.join(sorted(unknown))}")
    bboxes = [tuple(pilot["bbox"]) for pilot in config["pilots"]]
    sources = {source for pilot in config["pilots"] for source in pilot["sources"]}
    observations = _load(input_path, regions, bboxes, sources)
    history = _load(history_path, regions, bboxes, sources) if history_path else observations
    history_sha256 = (
        hashlib.sha256(history_path.read_bytes()).hexdigest() if history_path else input_sha256
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for pilot in config["pilots"]:
        started = time.perf_counter()
        tracemalloc.start()
        bbox = tuple(pilot["bbox"])
        start = date.fromisoformat(pilot["date_from"])
        end = date.fromisoformat(pilot["date_to"])
        historical_from = date.fromisoformat(pilot["historical_from"])
        historical_to = date.fromisoformat(pilot["historical_to"])
        if historical_to >= start:
            raise ValueError("historical_to must precede date_from")
        context_settings = pilot.get("context")
        if context_settings and date.fromisoformat(context_settings["as_of"]) > start:
            raise ValueError("context as_of must not follow date_from")
        context_features, context_sha256 = _context_source(context_settings)
        sources = set(pilot["sources"])
        selected = _select(observations, bbox, start, end, sources, pilot.get("region_code"))
        selected_history = _select(
            history,
            bbox,
            historical_from,
            historical_to,
            sources,
            pilot.get("region_code"),
        )
        clustering = cluster_incidents(
            selected,
            eps_km=pilot.get("eps_km", 5.0),
            time_window_hours=pilot.get("time_window_hours", 24.0),
            min_samples=pilot.get("min_samples", 2),
        )
        memory = ThermalMemory(selected_history, EqualAreaGrid(pilot.get("cell_km", 2.0)))
        rows = []
        context_coverage = {"partial_coverage": 0, "outside_coverage": 0, "unavailable": 0}
        for incident in clustering.incidents:
            profile = (
                memory.profile(
                    incident.longitude,
                    incident.latitude,
                    incident.first_seen,
                    datetime.combine(historical_from, datetime.min.time(), UTC),
                    region=incident.region,
                )
                if selected_history
                else None
            )
            context, context_inputs = _incident_context(
                incident.longitude, incident.latitude, context_settings, context_features
            )
            context_coverage[context["status"]] += 1
            rows.append(
                {
                    **asdict(incident),
                    "first_seen": incident.first_seen.isoformat(),
                    "last_seen": incident.last_seen.isoformat(),
                    "thermal_memory": (
                        {
                            **asdict(profile),
                            "last_seen_before_event": (
                                profile.last_seen_before_event.isoformat()
                                if profile.last_seen_before_event
                                else None
                            ),
                        }
                        if profile
                        else None
                    ),
                    "context": context,
                    "confidence_inputs": incident_features(
                        incident, selected, profile, context_inputs
                    ),
                }
            )
        output = output_dir / f"{pilot['name']}.incidents.jsonl"
        content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        output.write_text(content, encoding="utf-8")
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        results.append(
            {
                **pilot,
                "number_of_observations": len(selected),
                "historical_observations": len(selected_history),
                "number_of_incidents": len(clustering.incidents),
                "noise_observations": len(clustering.noise_ids),
                "thermal_memory_available": bool(selected_history),
                "context_feature_count": len(context_features),
                "context_sha256": context_sha256,
                "context_coverage": context_coverage,
                "number_of_grid_cells": len(memory.by_cell),
                "runtime_seconds": round(time.perf_counter() - started, 3),
                "peak_python_allocation_bytes": peak_bytes,
                "output": str(output),
                "output_sha256": hashlib.sha256(content.encode()).hexdigest(),
            }
        )
    manifest = {
        "processing_version": "research-1.1",
        "created_at": datetime.now(UTC).isoformat(),
        "input": str(input_path),
        "input_sha256": input_sha256,
        "history_input": str(history_path) if history_path else str(input_path),
        "history_sha256": history_sha256,
        "config": str(config_path),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "region_file": str(regions_path) if regions_path else None,
        "region_sha256": region_sha256,
        "pilots": results,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="kroma-pilot")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--regions", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = run(
            args.input, args.config, args.output_dir, args.manifest, args.history, args.regions
        )
    except (KeyError, OSError, ValueError) as error:
        parser.error(str(error))
    for pilot in manifest["pilots"]:
        name = pilot["name"]
        observations = pilot["number_of_observations"]
        incidents = pilot["number_of_incidents"]
        print(f"{name}: {observations} observations, {incidents} incidents")


if __name__ == "__main__":
    main()
