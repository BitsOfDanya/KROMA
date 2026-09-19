import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ml" / "src"))

from kroma_geo.raster_vector import (
    ChipGeoreference,
    class_features,
    point_features,
    to_wgs84,
)
from kroma_ml import service
from kroma_ml.artifacts import AF_VERSION, BS_VERSION

OUT_ROOT = REPO / "backend" / "app" / "prepared_data"
SEVERITY = {1: "low", 2: "moderate", 3: "high"}


def read_meta(kind: str) -> list[dict]:
    path = service.data_root("train") / kind / "meta.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def georef(row: dict) -> ChipGeoreference:
    gsd = float(row["gsd"])
    return ChipGeoreference(
        epsg=int(float(row["epsg"])),
        x_min=float(row["x_min"]),
        y_max=float(row["y_max"]),
        gsd_x=gsd,
        gsd_y=gsd,
    )


def footprint(row: dict) -> dict:
    ref = georef(row)
    size = int(row["width"]) * ref.gsd_x
    return mapping(
        to_wgs84(box(ref.x_min, ref.y_max - size, ref.x_min + size, ref.y_max), ref.epsg)
    )


def pick(rows: list[dict], count: int) -> list[dict]:
    if len(rows) <= count:
        return rows
    step = len(rows) / count
    return [rows[int(index * step)] for index in range(count)]


def write_json(path: Path, payload: dict) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def day(value: str) -> date:
    return date.fromisoformat(value[:10])


def build(args: argparse.Namespace) -> None:
    bs_rows = [
        row
        for row in read_meta("bs")
        if row["date_post"] not in ("", "nan")
        and float(row["valid_frac"] or 0) >= 0.85
        and float(row["burn_area_ha"] or 0) >= 150
    ]
    bs_rows.sort(key=lambda row: float(row["burn_area_ha"]), reverse=True)
    bs_rows = sorted(pick(bs_rows, args.bs), key=lambda row: row["chip_id"])
    af_rows = [
        row
        for row in read_meta("af")
        if float(row["n_fire_px"] or 0) >= 10 and float(row["valid_frac"] or 0) >= 0.9
    ]
    af_rows = sorted(
        pick(sorted(af_rows, key=lambda row: row["chip_id"]), args.af), key=lambda r: r["chip_id"]
    )

    model_zones, reference_zones, hotspots, scenes = [], [], [], []
    for row in bs_rows:
        chip_id, ref = row["chip_id"], georef(row)
        result = service.predict_bs(chip_id)
        after = f"{row['date_post']}T09:00:00Z"
        scenes.append(
            {
                "scene_id": chip_id,
                "satellite": "Sentinel-2",
                "acquired_at": after,
                "role": "after",
                "cloud_cover_pct": round(float(row["cloud_frac"] or 0) * 100, 1),
            }
        )
        for target, mask, version, source in (
            (model_zones, result["mask"], BS_VERSION, "final_model_in_sample"),
            (
                reference_zones,
                result["gt_mask"],
                "official_train_gt",
                "official_train_ground_truth",
            ),
        ):
            for feature in class_features(
                mask, ref, classes=SEVERITY, scene_id=chip_id, model_version=version, source=source
            ):
                feature["properties"].update(
                    {
                        "burn_event_id": row["fire_event_id"] or chip_id,
                        "assessment_id": f"ASSESS-{chip_id}-{source}",
                        "after_acquired_at": after,
                        "is_complete": True,
                        "scene_ids": [chip_id],
                    }
                )
                target.append(feature)
        print("bs", chip_id, result["total_burned_area_ha"], flush=True)
    for row in af_rows:
        chip_id, ref = row["chip_id"], georef(row)
        result = service.predict_af(chip_id)
        acquired = row["acq_datetime"].replace("+00:00", "Z")
        scenes.append(
            {
                "scene_id": chip_id,
                "satellite": row["satellite"],
                "acquired_at": acquired,
                "role": "observation",
                "cloud_cover_pct": None,
            }
        )
        for feature in point_features(
            result["mask"],
            ref,
            scene_id=chip_id,
            model_version=AF_VERSION,
            source="af_final_model_in_sample",
            values=result["probability"],
            limit=args.points_per_chip,
        ):
            feature["properties"].update(
                {
                    "acquired_at": acquired,
                    "satellite": row["satellite"],
                    "instrument": "VIIRS",
                    "frp_mw": None,
                }
            )
            hotspots.append(feature)
        print("af", chip_id, result["fire_pixels"], flush=True)

    af_cover = unary_union([shape(footprint(row)) for row in af_rows])
    bs_cover = unary_union([shape(footprint(row)) for row in bs_rows])
    extent = unary_union([af_cover, bs_cover]).bounds
    dates = sorted(day(scene["acquired_at"]) for scene in scenes)
    example_row = bs_rows[0]
    example_box = shape(footprint(example_row)).bounds
    example_day = day(f"{example_row['date_post']}")

    for suffix, zones, origin, name, description in (
        (
            "model",
            model_zones,
            "model_output",
            "KROMA: выход финальной модели на official train",
            "Контуры гарей и термоточки финальных AF/BS моделей на выбранных train-чипах. "
            "In-sample: модель обучена на всех train-чипах, метрики обобщения см. в отчёте.",
        ),
        (
            "reference",
            reference_zones,
            "reference",
            "KROMA: эталонная разметка official train",
            "Эталонные контуры severity из официальной разметки train-чипов (без модели).",
        ),
    ):
        folder = OUT_ROOT / f"kroma-official-train-{suffix}"
        folder.mkdir(parents=True, exist_ok=True)
        hot = write_json(
            folder / "hotspots.geojson",
            {"type": "FeatureCollection", "features": hotspots if suffix == "model" else []},
        )
        burn = write_json(
            folder / "burn_zones.geojson", {"type": "FeatureCollection", "features": zones}
        )
        manifest = {
            "schema_version": "1.0",
            "dataset_id": f"kroma-official-train-{suffix}",
            "dataset_version": "v005",
            "name": name,
            "description": description,
            "origin": origin,
            "processing_version": BS_VERSION if suffix == "model" else "official_train_gt",
            "available_from": dates[0].isoformat(),
            "available_to": dates[-1].isoformat(),
            "extent": [round(v, 6) for v in extent],
            "af_coverage": mapping(af_cover),
            "bs_coverage": mapping(bs_cover),
            "bs_valid_coverage": mapping(bs_cover),
            "area_crs": "EPSG:6933",
            "source_crs": "EPSG:4326",
            "mask": {
                "classes": {"0": "unburned", "1": "low", "2": "moderate", "3": "high"},
                "nodata": 255,
                "resolution_m": [20, 20],
                "validity": "bs_coverage polygon",
            },
            "observation_source": "Official competition train chips (Sentinel-2/VIIRS)",
            "temporal_rule": (
                "Hotspots use acquired_at; burn zones use after_acquired_at; "
                "both use inclusive UTC calendar dates."
            ),
            "license": "Official competition data, non-commercial demo use",
            "attribution": "KROMA, official КосмоХакатон 2026 train data",
            "distribution": "Derived contours only; source rasters are not redistributed.",
            "example": {
                "bbox": [round(v, 6) for v in example_box],
                "from": example_day.isoformat(),
                "to": example_day.isoformat(),
            },
            "scenes": scenes,
            "artifacts": {
                "hotspots": {"path": "hotspots.geojson", "sha256": hot},
                "burn_zones": {"path": "burn_zones.geojson", "sha256": burn},
            },
        }
        (folder / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "wrote",
            folder.relative_to(REPO),
            len(zones),
            "zones",
            len(manifest["scenes"]),
            "scenes",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bs", type=int, default=14)
    parser.add_argument("--af", type=int, default=18)
    parser.add_argument("--points-per-chip", type=int, default=400)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
