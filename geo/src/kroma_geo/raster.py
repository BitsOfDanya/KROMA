from collections import Counter
from pathlib import Path
from typing import Any

WORLDCOVER_CLASSES = {
    10: "forest",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare",
    70: "snow_ice",
    80: "water",
    90: "wetland",
    95: "mangroves",
    100: "moss_lichen",
}


def land_cover_at(path: Path, longitude: float, latitude: float) -> str | None:
    import rasterio
    from rasterio.warp import transform

    with rasterio.open(path) as dataset:
        x, y = transform("EPSG:4326", dataset.crs, [longitude], [latitude])
        sample = next(dataset.sample([(x[0], y[0])], masked=True))[0]
        if bool(getattr(sample, "mask", False)):
            return None
        value = int(sample)
        if dataset.nodata is not None and value == dataset.nodata:
            return None
        return WORLDCOVER_CLASSES.get(value)


def land_cover_composition(path: Path, geometry: dict[str, Any]) -> dict[str, float]:
    import rasterio
    from rasterio.mask import mask
    from rasterio.warp import transform_geom

    with rasterio.open(path) as dataset:
        projected = transform_geom("EPSG:4326", dataset.crs, geometry)
        try:
            clipped, _ = mask(dataset, [projected], crop=True, filled=False)
        except ValueError:
            return {}
        counts = Counter(
            WORLDCOVER_CLASSES[int(value)]
            for value in clipped[0].compressed()
            if int(value) in WORLDCOVER_CLASSES
        )
    total = sum(counts.values())
    return {name: count / total for name, count in sorted(counts.items())} if total else {}


def dominant_land_cover(composition: dict[str, float]) -> str | None:
    return max(composition, key=lambda name: (composition[name], name)) if composition else None


def ndvi(nir: float, red: float) -> float | None:
    denominator = nir + red
    return (nir - red) / denominator if denominator else None


def nbr(nir: float, swir: float) -> float | None:
    denominator = nir + swir
    return (nir - swir) / denominator if denominator else None
