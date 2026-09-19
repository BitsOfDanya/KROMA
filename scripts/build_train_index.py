#!/usr/bin/env python3
"""Построить индекс OFFICIAL TRAIN из meta.csv → GeoJSON + JSON для API/карты.

Использует UTM bounds из meta (не восстанавливает test).
"""
from __future__ import annotations

import csv
import io
import json
import math
import tarfile
from pathlib import Path

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


def footprint(epsg: int, x_min: float, y_min: float, x_max: float, y_max: float) -> list[list[float]]:
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
    ring = footprint(epsg, x_min, y_min, x_max, y_max)  # type: ignore[arg-type]
    n_fire = _num(row.get("n_fire_px", ""))
    burn_ha = _num(row.get("burn_area_ha", ""))
    sev1, sev2, sev3 = _num(row.get("sev1_px", "")), _num(row.get("sev2_px", "")), _num(row.get("sev3_px", ""))
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
    if not TAR.exists():
        raise SystemExit(f"missing {TAR}")
    features: list[dict] = []
    with tarfile.open(TAR, "r:") as tf:
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
