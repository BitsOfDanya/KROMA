#!/usr/bin/env python3
"""Собрать footprints train-чипов Мониторинг DATA → GeoJSON для карты.

Читает (в т.ч. частично скачанный) data/yandex/fire-train-renamed.tar,
извлекает train/*/aux/*_AUX.tif с GeoTIFF-привязкой UTM 37N/38N и пишет
frontend/public/data/monitoring_chips.geojson.

Test-чипы намеренно без геопривязки — на карту не кладутся.
"""
from __future__ import annotations

import json
import math
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAR = ROOT / "data/yandex/fire-train-renamed.tar"
OUT_PUBLIC = ROOT / "frontend/public/data/monitoring_chips.geojson"
OUT_DATA = ROOT / "data/fire-aoi/monitoring_chips.geojson"
TMP = ROOT / "data/yandex/chips_aux"


def utm_to_lonlat(
    easting: float,
    northing: float,
    zone: int,
    northern: bool = True,
) -> tuple[float, float]:
    a = 6378137.0
    e = 0.081819190842622
    e1sq = 0.006739496742333
    k0 = 0.9996
    x = easting - 500000.0
    y = northing if northern else northing - 10000000.0
    m = y / k0
    mu = m / (a * (1 - e**2 / 4 - 3 * e**4 / 64 - 5 * e**6 / 256))
    e1 = (1 - math.sqrt(1 - e**2)) / (1 + math.sqrt(1 - e**2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = (
        mu
        + j1 * math.sin(2 * mu)
        + j2 * math.sin(4 * mu)
        + j3 * math.sin(6 * mu)
        + j4 * math.sin(8 * mu)
    )
    sinfp = math.sin(fp)
    cosfp = math.cos(fp)
    tanfp = math.tan(fp)
    c1 = e1sq * cosfp**2
    t1 = tanfp**2
    r1 = a * (1 - e**2) / ((1 - e**2 * sinfp**2) ** 1.5)
    n1 = a / math.sqrt(1 - e**2 * sinfp**2)
    d = x / (n1 * k0)
    q1 = n1 * tanfp / r1
    q2 = d**2 / 2
    q3 = (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e1sq) * d**4 / 24
    q4 = (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e1sq - 3 * c1**2) * d**6 / 720
    lat = fp - q1 * (q2 - q3 + q4)
    q5 = d
    q6 = (1 + 2 * t1 + c1) * d**3 / 6
    q7 = (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e1sq + 24 * t1**2) * d**5 / 120
    lon = (q5 - q6 + q7) / cosfp
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    return math.degrees(lon) + math.degrees(lon0), math.degrees(lat)


def read_geotiff_georef(path: pathlib.Path) -> dict | None:
    data = path.read_bytes()
    bo = "<" if data[:2] == b"II" else ">"
    ifd = struct.unpack(bo + "I", data[4:8])[0]
    n = struct.unpack(bo + "H", data[ifd : ifd + 2])[0]
    width = height = None
    scale = tie = None
    ascii_params = ""
    for i in range(n):
        off = ifd + 2 + i * 12
        tag, typ, count, val = struct.unpack(bo + "HHII", data[off : off + 12])
        if tag == 256:
            width = val
        elif tag == 257:
            height = val
        elif tag == 33550 and typ == 12:
            scale = struct.unpack(bo + f"{count}d", data[val : val + count * 8])
        elif tag == 33922 and typ == 12:
            tie = struct.unpack(bo + f"{count}d", data[val : val + count * 8])
        elif tag == 34737 and typ == 2:
            ascii_params = data[val : val + count].split(b"\0")[0].decode("ascii", "replace")
    if not (width and height and scale and tie):
        return None
    zone = 37 if "UTM zone 37" in ascii_params else 38 if "UTM zone 38" in ascii_params else None
    if zone is None:
        return None
    x0, y0 = tie[3], tie[4]
    sx, sy = scale[0], scale[1]
    corners_utm = [
        (x0, y0),
        (x0 + width * sx, y0),
        (x0 + width * sx, y0 - height * sy),
        (x0, y0 - height * sy),
        (x0, y0),
    ]
    return {
        "width": width,
        "height": height,
        "gsd_m": sx,
        "utm_zone": zone,
        "crs": ascii_params.split("|")[0],
        "coordinates": [[list(utm_to_lonlat(x, y, zone)) for x, y in corners_utm]],
    }


def extract_aux(tar_path: pathlib.Path, dest_dir: pathlib.Path) -> list[pathlib.Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[pathlib.Path] = []
    size = tar_path.stat().st_size
    with open(tar_path, "rb") as f:
        off = 0
        while off + 512 <= size:
            f.seek(off)
            block = f.read(512)
            if len(block) < 512 or block == b"\0" * 512:
                break
            name = block[0:100].split(b"\0", 1)[0].decode("utf-8", "replace")
            if not name:
                break
            size_s = block[124:136].split(b"\0", 1)[0].strip()
            try:
                fsize = int(size_s, 8) if size_s else 0
            except ValueError:
                break
            typ = block[156:157]
            data_start = off + 512
            data_end = data_start + fsize
            if data_end > size:
                print(f"truncated at {name}", file=sys.stderr)
                break
            if (
                typ in (b"0", b"\0")
                and name.startswith("train/")
                and "/aux/" in name
                and name.endswith("_AUX.tif")
            ):
                dest = dest_dir / pathlib.Path(name).name
                if not dest.exists() or dest.stat().st_size != fsize:
                    f.seek(data_start)
                    dest.write_bytes(f.read(fsize))
                extracted.append(dest)
            off = data_start + ((fsize + 511) // 512) * 512
    return extracted


def main() -> int:
    if not TAR.exists():
        print(f"missing {TAR}", file=sys.stderr)
        return 1
    paths = extract_aux(TAR, TMP)
    print(f"aux: {len(paths)} from {TAR.name} ({TAR.stat().st_size} bytes)")
    features = []
    for path in sorted(set(paths)):
        geo = read_geotiff_georef(path)
        if not geo:
            continue
        chip_id = path.name.replace("_AUX.tif", "")
        if chip_id.startswith("AF_"):
            kind = "af"
        elif chip_id.startswith("BS_"):
            kind = "bs"
        else:
            kind = "unknown"
        features.append(
            {
                "type": "Feature",
                "id": chip_id,
                "properties": {
                    "id": chip_id,
                    "chip_id": chip_id,
                    "kind": kind,
                    "task": kind,
                    "split": "train",
                    "utm_zone": geo["utm_zone"],
                    "gsd_m": geo["gsd_m"],
                    "width": geo["width"],
                    "height": geo["height"],
                    "crs": geo["crs"],
                    "source": "Мониторинг DATA · train",
                },
                "geometry": {"type": "Polygon", "coordinates": geo["coordinates"]},
            }
        )
    fc = {"type": "FeatureCollection", "name": "monitoring_chips_train", "features": features}
    text = json.dumps(fc, ensure_ascii=False)
    OUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_PUBLIC.write_text(text, encoding="utf-8")
    OUT_DATA.write_text(text, encoding="utf-8")
    print(f"wrote {len(features)} footprints → {OUT_PUBLIC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
