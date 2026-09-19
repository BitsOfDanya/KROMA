import numpy as np
import pandas as pd
from kroma_ml.af_data import AUX_BANDS, VIIRS_BANDS, load_chip, load_meta, tile_key_map
from scipy.ndimage import median_filter, uniform_filter

WINDOWS = (3, 5, 7, 11)
RNG = np.random.default_rng(42)
BG_SAMPLE_PER_CHIP = 500


def local_stats(x: np.ndarray, size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = uniform_filter(x, size=size, mode="reflect")
    sq_mean = uniform_filter(x * x, size=size, mode="reflect")
    std = np.sqrt(np.maximum(sq_mean - mean * mean, 0.0))
    med = median_filter(x, size=size, mode="reflect")
    return mean, std, med


def build_pixel_table(meta: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for chip_id in meta["chip_id"]:
        chip = load_chip(chip_id)
        if chip.mask is None:
            continue
        valid = np.isfinite(chip.viirs).all(axis=-1) & (chip.band("valid") > 0.5)
        fire = (chip.mask == 1) & valid
        bg = (chip.mask == 0) & valid
        i4 = chip.band("I4")
        i5 = chip.band("I5")
        diff = i4 - i5
        local = {}
        for size in WINDOWS:
            mean4, std4, med4 = local_stats(i4, size)
            meanD, stdD, medD = local_stats(diff, size)
            local[size] = (mean4, std4, med4, meanD, stdD, medD)

        def rows_from_mask(mask_arr: np.ndarray, label: int, cap: int | None) -> None:
            ys, xs = np.nonzero(mask_arr)
            if cap is not None and len(ys) > cap:
                pick = RNG.choice(len(ys), size=cap, replace=False)
                ys, xs = ys[pick], xs[pick]
            for y, x in zip(ys, xs, strict=True):
                row = {
                    "chip_id": chip_id,
                    "fire": label,
                    "satellite": chip_meta_satellite,
                }
                for i, name in enumerate(VIIRS_BANDS):
                    row[name] = float(chip.viirs[y, x, i])
                for i, name in enumerate(AUX_BANDS):
                    row[f"aux_{name}"] = float(chip.aux[y, x, i])
                row["I4_I5"] = float(diff[y, x])
                for size in WINDOWS:
                    mean4, std4, med4, meanD, stdD, medD = local[size]
                    row[f"I4_localmean_{size}"] = float(mean4[y, x])
                    row[f"I4_localstd_{size}"] = float(std4[y, x])
                    row[f"I4_localmed_{size}"] = float(med4[y, x])
                    row[f"I4_minus_localmed_{size}"] = float(i4[y, x] - med4[y, x])
                    row[f"D_localmed_{size}"] = float(medD[y, x])
                    row[f"D_localstd_{size}"] = float(stdD[y, x])
                    row[f"D_minus_localmed_{size}"] = float(diff[y, x] - medD[y, x])
                rows.append(row)

        chip_meta_satellite = meta.loc[meta["chip_id"] == chip_id, "satellite"].iloc[0]
        rows_from_mask(fire, 1, None)
        rows_from_mask(bg, 0, BG_SAMPLE_PER_CHIP)
    return pd.DataFrame(rows)


def main() -> None:
    meta = load_meta()
    print("=== META SHAPE ===", meta.shape)
    print("=== KIND ===\n", meta["kind"].value_counts())
    print("=== SATELLITE ===\n", meta["satellite"].value_counts())
    print("=== EPSG ===\n", meta["epsg"].value_counts())
    print("=== POSITIVE / NEGATIVE CHIPS ===")
    print(
        "positive:",
        int((meta["n_fire_px"] > 0).sum()),
        "negative:",
        int((meta["n_fire_px"] == 0).sum()),
    )
    print("=== N_FIRE_PX DESCRIBE (all) ===\n", meta["n_fire_px"].describe())
    print(
        "=== N_FIRE_PX DESCRIBE (positive only) ===\n",
        meta.loc[meta["n_fire_px"] > 0, "n_fire_px"].describe(),
    )
    total_px = int(meta["width"].iloc[0]) * int(meta["height"].iloc[0]) * len(meta)
    total_fire = int(meta["n_fire_px"].sum())
    print(
        f"total pixels={total_px} total_fire_px={total_fire} fire_frac={total_fire / total_px:.6f}"
    )

    tiles = tile_key_map()
    print("=== TILE REUSE ===")
    print("unique tiles:", tiles.nunique(), "/", len(tiles))
    print(tiles.value_counts().describe())

    dup = meta["chip_id"].duplicated().sum()
    print("duplicate chip_id:", dup)
    print(
        "NaN in width/height/gsd/x_min:",
        meta[["width", "height", "gsd", "x_min"]].isna().sum().to_dict(),
    )

    print("\n=== BUILDING PIXEL TABLE (fire + background sample) ===")
    table = build_pixel_table(meta)
    print("pixel table shape:", table.shape)
    table.to_pickle("research/experiments/af_pixel_sample.pkl")

    fire = table[table["fire"] == 1]
    bg = table[table["fire"] == 0]

    for col in ["I1", "I2", "I3", "I4", "I5", "I4_I5", "solar_zenith", "sensor_zenith"]:
        print(f"\n--- {col} ---")
        print("fire  :", fire[col].describe()[["mean", "std", "min", "50%", "max"]].to_dict())
        print("bg    :", bg[col].describe()[["mean", "std", "min", "50%", "max"]].to_dict())

    for size in WINDOWS:
        col = f"I4_minus_localmed_{size}"
        print(f"\n--- {col} ---")
        print("fire  :", fire[col].describe()[["mean", "std", "50%"]].to_dict())
        print("bg    :", bg[col].describe()[["mean", "std", "50%"]].to_dict())
        col2 = f"D_minus_localmed_{size}"
        print(f"--- {col2} ---")
        print("fire  :", fire[col2].describe()[["mean", "std", "50%"]].to_dict())
        print("bg    :", bg[col2].describe()[["mean", "std", "50%"]].to_dict())

    for col in ["aux_landcover", "aux_dem", "aux_t2m", "aux_rh2m", "aux_wind_speed"]:
        print(f"\n--- {col} ---")
        print("fire  :", fire[col].describe()[["mean", "std", "50%"]].to_dict())
        print("bg    :", bg[col].describe()[["mean", "std", "50%"]].to_dict())

    print("\n=== FIRE COUNT BY SATELLITE ===")
    print(fire["satellite"].value_counts())
    print(bg["satellite"].value_counts())
    print("\n=== I4 mean by satellite (fire) ===")
    print(fire.groupby("satellite")["I4"].mean())
    print("\n=== I4 mean by satellite (bg) ===")
    print(bg.groupby("satellite")["I4"].mean())

    print("\n=== I4 saturation (>= 367) ===")
    print("fire frac saturated:", (fire["I4"] >= 367).mean())
    print("bg frac saturated:", (bg["I4"] >= 367).mean())


if __name__ == "__main__":
    main()
