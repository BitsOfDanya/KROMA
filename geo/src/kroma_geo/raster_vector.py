from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from pyproj import Transformer
from shapely import box
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

SQUARE_METRES_PER_HECTARE = 10_000.0


@dataclass(frozen=True)
class ChipGeoreference:
    epsg: int
    x_min: float
    y_max: float
    gsd_x: float
    gsd_y: float

    @property
    def pixel_area_m2(self) -> float:
        return self.gsd_x * self.gsd_y


def pixel_area_ha(pixel_count: int, georef: ChipGeoreference) -> float:
    return pixel_count * georef.pixel_area_m2 / SQUARE_METRES_PER_HECTARE


def _merged_boxes(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    height = binary.shape[0]
    open_runs: dict[tuple[int, int], int] = {}
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(height + 1):
        current: set[tuple[int, int]] = set()
        if row < height:
            padded = np.concatenate(([0], binary[row].astype(np.int8), [0]))
            edges = np.diff(padded)
            current = set(
                zip(
                    np.nonzero(edges == 1)[0].tolist(),
                    np.nonzero(edges == -1)[0].tolist(),
                    strict=True,
                )
            )
        for key in [key for key in open_runs if key not in current]:
            boxes.append((key[0], open_runs.pop(key), key[1], row))
        for key in current:
            open_runs.setdefault(key, row)
    return boxes


def mask_polygon(binary: np.ndarray, georef: ChipGeoreference) -> BaseGeometry | None:
    boxes = _merged_boxes(np.asarray(binary, dtype=bool))
    if not boxes:
        return None
    return unary_union(
        [
            box(
                georef.x_min + c0 * georef.gsd_x,
                georef.y_max - r1 * georef.gsd_y,
                georef.x_min + c1 * georef.gsd_x,
                georef.y_max - r0 * georef.gsd_y,
            )
            for c0, r0, c1, r1 in boxes
        ]
    )


@lru_cache(maxsize=32)
def wgs84_transformer(epsg: int) -> Transformer:
    return Transformer.from_crs(epsg, 4326, always_xy=True)


def to_wgs84(geometry: BaseGeometry, epsg: int) -> BaseGeometry:
    transformer = wgs84_transformer(epsg)
    return shapely_transform(transformer.transform, geometry)


def class_features(
    mask: np.ndarray,
    georef: ChipGeoreference,
    *,
    classes: dict[int, str],
    scene_id: str,
    model_version: str,
    source: str,
    simplify_m: float = 0.0,
) -> list[dict]:
    features: list[dict] = []
    for class_id, severity in classes.items():
        binary = mask == class_id
        if not binary.any():
            continue
        geometry = mask_polygon(binary, georef)
        parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        total_ha = pixel_area_ha(int(binary.sum()), georef)
        for index, part in enumerate(sorted(parts, key=lambda p: (-p.area, p.bounds)), start=1):
            area_ha = round(part.area / SQUARE_METRES_PER_HECTARE, 4)
            shown = part.simplify(simplify_m, preserve_topology=True) if simplify_m else part
            features.append(
                {
                    "type": "Feature",
                    "id": f"{scene_id}-C{class_id}-{index:03d}",
                    "geometry": mapping(
                        to_wgs84(shown.segmentize(min(georef.gsd_x, georef.gsd_y)), georef.epsg)
                    ),
                    "properties": {
                        "id": f"{scene_id}-C{class_id}-{index:03d}",
                        "contour_id": f"{scene_id}-C{class_id}-{index:03d}",
                        "scene_id": scene_id,
                        "class_id": class_id,
                        "severity": severity,
                        "area_ha": area_ha,
                        "class_area_ha": round(total_ha, 4),
                        "model_version": model_version,
                        "source": source,
                    },
                }
            )
    return features


def point_features(
    mask: np.ndarray,
    georef: ChipGeoreference,
    *,
    scene_id: str,
    model_version: str,
    source: str,
    values: np.ndarray | None = None,
    limit: int = 5000,
) -> list[dict]:
    rows, cols = np.nonzero(mask)
    if len(rows) > limit:
        keep = np.linspace(0, len(rows) - 1, limit).astype(int)
        rows, cols = rows[keep], cols[keep]
    transformer = wgs84_transformer(georef.epsg)
    xs = georef.x_min + (cols + 0.5) * georef.gsd_x
    ys = georef.y_max - (rows + 0.5) * georef.gsd_y
    lons, lats = transformer.transform(xs, ys)
    out = []
    for n, (lon, lat, row, col) in enumerate(zip(lons, lats, rows, cols, strict=True), start=1):
        props = {
            "id": f"{scene_id}-P{n:04d}",
            "scene_id": scene_id,
            "row": int(row),
            "col": int(col),
            "model_version": model_version,
            "source": source,
        }
        if values is not None:
            props["confidence"] = round(float(values[row, col]), 4)
        out.append(
            {
                "type": "Feature",
                "id": props["id"],
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": props,
            }
        )
    return out
