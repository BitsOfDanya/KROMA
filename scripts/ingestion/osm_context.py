import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

ENDPOINT = "https://overpass-api.de/api/interpreter"
FILTERS = {
    "settlement": 'nwr["place"~"^(city|town|village|hamlet)$"]',
    "road": 'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|residential|service)$"]',
    "power_line": 'way["power"="line"]',
    "industrial": 'nwr["landuse"="industrial"]',
    "airport": 'nwr["aeroway"="aerodrome"]',
    "railway": 'way["railway"="rail"]',
    "protected_area": 'nwr["boundary"="protected_area"]',
}


def build_query(
    bbox: tuple[float, float, float, float],
    as_of: date | None,
    categories: list[str],
) -> str:
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("bbox must be west south east north")
    if not categories or any(category not in FILTERS for category in categories):
        raise ValueError("unknown or empty OSM category")
    bounds = ",".join(format(value, "g") for value in (south, west, north, east))
    historical = f'[date:"{as_of.isoformat()}T23:59:59Z"]' if as_of else ""
    statements = "".join(f"{FILTERS[category]}({bounds});" for category in categories)
    return f"[out:json][timeout:90]{historical};({statements});out geom;"


def _category(tags: dict[str, str]) -> str | None:
    if tags.get("place") in {"city", "town", "village", "hamlet"}:
        return "settlement"
    if "highway" in tags:
        return "road"
    if tags.get("power") == "line":
        return "power_line"
    if tags.get("landuse") == "industrial":
        return "industrial"
    if tags.get("aeroway") == "aerodrome":
        return "airport"
    if tags.get("railway") == "rail":
        return "railway"
    if tags.get("boundary") == "protected_area":
        return "protected_area"
    return None


def _geometry(element: dict[str, Any], category: str) -> dict[str, Any] | None:
    if element["type"] == "node":
        return {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
    if element["type"] == "way":
        coordinates = [[point["lon"], point["lat"]] for point in element.get("geometry", ())]
        if len(coordinates) < 2:
            return None
        if coordinates[0] == coordinates[-1] and category in {
            "industrial",
            "airport",
            "protected_area",
            "settlement",
        }:
            return {"type": "Polygon", "coordinates": [coordinates]}
        return {"type": "LineString", "coordinates": coordinates}
    return None


def to_features(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features = []
    for element in elements:
        tags = element.get("tags") or {}
        category = _category(tags)
        if category is None:
            continue
        geometry = _geometry(element, category)
        if geometry is None:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"{element['type']}/{element['id']}",
                "properties": {"category": category, "name": tags.get("name"), "tags": tags},
                "geometry": geometry,
            }
        )
    return features


def run(args: argparse.Namespace) -> dict[str, Any]:
    bbox = tuple(args.bbox)
    query = build_query(bbox, args.as_of, args.categories)
    query_sha256 = hashlib.sha256(query.encode()).hexdigest()
    raw = Path("data/raw/osm") / f"{query_sha256[:20]}.json"
    cached = raw.exists()
    if not cached:
        response = httpx.post(
            ENDPOINT,
            data={"data": query},
            headers={"User-Agent": "KROMA-research/0.1"},
            timeout=120,
        )
        response.raise_for_status()
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(response.content)
    data = json.loads(raw.read_text(encoding="utf-8"))
    if "elements" not in data:
        raise ValueError("Overpass response has no elements")
    features = to_features(data["elements"])
    collection = {"type": "FeatureCollection", "features": features}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(collection, sort_keys=True) + "\n"
    args.output.write_text(content, encoding="utf-8")
    manifest = {
        "processing_version": "osm-context-1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": ENDPOINT,
        "bbox": bbox,
        "as_of": args.as_of.isoformat() if args.as_of else None,
        "categories": args.categories,
        "query_sha256": query_sha256,
        "raw_path": str(raw),
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "cached": cached,
        "osm_base_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "feature_count": len(features),
        "category_counts": dict(
            sorted(Counter(feature["properties"]["category"] for feature in features).items())
        ),
        "output_sha256": hashlib.sha256(content.encode()).hexdigest(),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="osm-context")
    parser.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--category", action="append", choices=sorted(FILTERS), dest="categories")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    args.categories = args.categories or list(FILTERS)
    try:
        manifest = run(args)
    except (httpx.HTTPError, KeyError, OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Wrote {manifest['feature_count']} OSM features to {args.output}")


if __name__ == "__main__":
    main()
