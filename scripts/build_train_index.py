from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import tarfile
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
TAR = ROOT / "data/yandex/fire-train-renamed.tar"
OUT_GEOJSON = ROOT / "frontend/public/data/monitoring_chips.geojson"
OUT_INDEX = ROOT / "data/fire-aoi/train_chips_index.json"
OUT_GEOJSON_DATA = ROOT / "data/fire-aoi/monitoring_chips.geojson"

_transformers: dict[int, Transformer] = {}


def transformer(epsg: int) -> Transformer:
    if epsg not in _transformers:
        _transformers[epsg] = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return _transformers[epsg]


def footprint(
    epsg: int,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> list[list[float]]:
    t = transformer(epsg)
    corners = [
        (x_min, y_max),
        (x_max, y_max),
        (x_max, y_min),
        (x_min, y_min),
        (x_min, y_max),
    ]
    return [list(t.transform(x, y)) for x, y in corners]


def _num(value: str) -> float | None:
    if value in ("", "nan", "NaN", "None", None):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str) -> int | None:
    n = _num(value)
    return int(n) if n is not None and math.isfinite(n) else None


def _str(value: str) -> str | None:
    if value in ("", "nan", "NaN", "None", None):
        return None
    return value


def read_meta(tf: tarfile.TarFile, member: str) -> list[dict]:
    raw = tf.extractfile(member)
    assert raw is not None
    rows = list(csv.DictReader(io.StringIO(raw.read().decode("utf-8"))))
    return rows


def row_to_feature(row: dict) -> dict | None:
    chip_id = row["chip_id"]
    kind = row["kind"]
    epsg = _int(row["epsg"])
    x_min, y_min = _num(row["x_min"]), _num(row["y_min"])
    x_max, y_max = _num(row["x_max"]), _num(row["y_max"])
    if epsg is None or None in (x_min, y_min, x_max, y_max):
        return None
    ring = footprint(epsg, x_min, y_min, x_max, y_max)
    n_fire = _num(row.get("n_fire_px", ""))
    burn_ha = _num(row.get("burn_area_ha", ""))
    sev1 = _num(row.get("sev1_px", ""))
    sev2 = _num(row.get("sev2_px", ""))
    sev3 = _num(row.get("sev3_px", ""))
    props = {
        "id": chip_id,
        "chip_id": chip_id,
        "kind": kind,
        "task": kind,
        "split": "train",
        "origin": "official_train",
        "fire_event_id": _str(row.get("fire_event_id", "")),
        "epsg": epsg,
        "gsd_m": _num(row.get("gsd", "")),
        "width": _int(row.get("width", "")),
        "height": _int(row.get("height", "")),
        "acq_datetime": _str(row.get("acq_datetime", "")),
        "satellite": _str(row.get("satellite", "")),
        "date_pre": _str(row.get("date_pre", "")),
        "date_post": _str(row.get("date_post", "")),
        "s1_date_pre": _str(row.get("s1_date_pre", "")),
        "s1_date_post": _str(row.get("s1_date_post", "")),
        "valid_frac": _num(row.get("valid_frac", "")),
        "cloud_frac": _num(row.get("cloud_frac", "")),
        "n_fire_px": n_fire,
        "has_fire": bool(n_fire and n_fire > 0) if kind == "af" else None,
        "burn_area_ha": burn_ha,
        "sev1_px": sev1,
        "sev2_px": sev2,
        "sev3_px": sev3,
        "source": "Мониторинг DATA · official train",
    }
    return {
        "type": "Feature",
        "id": chip_id,
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train-root",
        type=Path,
        default=Path(os.environ.get("KROMA_TRAIN_ROOT") or ROOT / "data/Мониторинг DATA/train"),
    )
    parser.add_argument("--tar", type=Path, default=TAR)
    args = parser.parse_args()
    features: list[dict] = []
    if args.train_root.is_dir():
        for kind in ("af", "bs"):
            with (args.train_root / kind / "meta.csv").open() as handle:
                for row in csv.DictReader(handle):
                    if "_tr_" not in row["chip_id"]:
                        raise ValueError("Only official TRAIN may be georeferenced")
                    path = args.train_root / kind / "masks" / f"{row['chip_id']}_MASK.tif"
                    with rasterio.open(path) as raster:
                        if not raster.crs or not raster.crs.is_projected:
                            raise ValueError(f"Projected CRS required: {path.name}")
                        mask = raster.read(1)
                        bounds = raster.bounds
                        row.update(
                            kind=kind,
                            epsg=str(raster.crs.to_epsg()),
                            x_min=str(bounds.left),
                            y_min=str(bounds.bottom),
                            x_max=str(bounds.right),
                            y_max=str(bounds.top),
                            gsd=str(abs(raster.transform.a)),
                            width=str(raster.width),
                            height=str(raster.height),
                        )
                        area = (
                            abs(
                                raster.transform.a * raster.transform.e
                                - raster.transform.b * raster.transform.d
                            )
                            / 10000
                        )
                        if kind == "bs":
                            row["burn_area_ha"] = str(
                                round(float(np.isin(mask, (1, 2, 3)).sum()) * area, 4)
                            )
                            for k in (1, 2, 3):
                                row[f"sev{k}_px"] = str(int((mask == k).sum()))
                        else:
                            row["n_fire_px"] = str(int((mask == 1).sum()))
                        feature = row_to_feature(row)
                        if feature:
                            feature["properties"]["transform"] = list(raster.transform)[:6]
                            feature["properties"]["area_ha"] = raster.width * raster.height * area
                            coords = feature["geometry"]["coordinates"][0]
                            feature["properties"]["bbox"] = [
                                min(c[0] for c in coords),
                                min(c[1] for c in coords),
                                max(c[0] for c in coords),
                                max(c[1] for c in coords),
                            ]
                            features.append(feature)
    else:
        with tarfile.open(args.tar, "r:") as tf:
            for member in ("train/af/meta.csv", "train/bs/meta.csv"):
                for row in read_meta(tf, member):
                    feat = row_to_feature(row)
                    if feat:
                        features.append(feat)
    features.sort(key=lambda f: f["id"])
    fc = {
        "type": "FeatureCollection",
        "name": "monitoring_chips_train",
        "features": features,
    }
    text = json.dumps(fc, ensure_ascii=False)
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(text, encoding="utf-8")
    OUT_GEOJSON_DATA.write_text(text, encoding="utf-8")
    index = {
        "dataset": "official_train",
        "source": "https://disk.yandex.ru/d/-rpmevTflbXZQg",
        "tar": str(TAR.relative_to(ROOT)),
        "counts": {
            "total": len(features),
            "af": sum(1 for f in features if f["properties"]["kind"] == "af"),
            "bs": sum(1 for f in features if f["properties"]["kind"] == "bs"),
        },
        "chips": [f["properties"] | {"geometry": f["geometry"]} for f in features],
    }
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(features)} chips → {OUT_GEOJSON.relative_to(ROOT)}")
    print(f"index → {OUT_INDEX.relative_to(ROOT)} ({index['counts']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
