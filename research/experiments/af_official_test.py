import argparse
import hashlib
import json
import resource
import statistics
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import tifffile
from kroma_ml.af_data import AUX_BANDS, VIIRS_BANDS, Chip, load_chip, load_meta, valid_mask
from kroma_ml.af_features import FEATURE_NAMES, chip_feature_stack, feature_indices
from kroma_ml.af_physics import predict as physics_predict
from scipy.ndimage import median_filter

TEST_ROOT = Path("data/test")
TRAIN_ROOT = Path("data/Мониторинг DATA/train/af")
EXPERIMENTS = Path("research/experiments")
ARTIFACTS = Path("artifacts")
FINAL_MODEL = EXPERIMENTS / "af_fulltrain_model.joblib"
CALIBRATION = EXPERIMENTS / "af_oof_calibration.json"
AF_SUBMISSION = ARTIFACTS / "af_submission.csv"
FEATURE_GROUPS = ("raw", "thermal", "landcover", "weather", "angles")
EXTRA_BANDS = ("I4_I5", "I4_minus_localmed_7")
CV_TAG = "thermal_valid"


def template_ids() -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    meta_path = TEST_ROOT / "meta.csv"
    sample_path = TEST_ROOT / "sample_submission.csv"
    if not meta_path.exists() or not sample_path.exists():
        raise FileNotFoundError("official test meta.csv or sample_submission.csv is missing")
    meta = pd.read_csv(meta_path)
    sample = pd.read_csv(sample_path, keep_default_na=False)
    if meta.chip_id.duplicated().any() or set(meta.kind) != {"af", "bs"}:
        raise ValueError("test metadata has duplicate chip IDs or unexpected kinds")
    if list(sample.columns) != ["chip_id", "class_id", "rle"]:
        raise ValueError("sample_submission columns must be chip_id,class_id,rle")
    af_ids = meta.loc[meta.kind == "af", "chip_id"].tolist()
    bs_ids = meta.loc[meta.kind == "bs", "chip_id"].tolist()
    expected = {(cid, 1) for cid in af_ids} | {
        (cid, class_id) for cid in bs_ids for class_id in (1, 2, 3)
    }
    actual = list(zip(sample.chip_id, sample.class_id, strict=True))
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("sample_submission pairs do not match official test metadata")
    af_meta = meta.loc[meta.kind == "af"]
    if not ((af_meta.width == 256) & (af_meta.height == 256)).all():
        raise ValueError("AF test metadata contains non-256 chips")
    for directory, suffix in (("viirs", "_VIIRS_I1-I5.tif"), ("aux", "_AUX.tif")):
        found = {
            path.name.removesuffix(suffix)
            for path in (TEST_ROOT / "af" / directory).glob(f"*{suffix}")
        }
        if found != set(af_ids):
            raise ValueError(f"AF test {directory} files do not match metadata IDs")
    ordered_af = sample.loc[sample.chip_id.isin(af_ids), "chip_id"].tolist()
    return meta, sample, ordered_af, bs_ids


def _read_tiff(path: Path, names: tuple[str, ...]) -> np.ndarray:
    with tifffile.TiffFile(path) as file:
        array = file.asarray()
        metadata = ET.fromstring(file.pages[0].tags[42112].value)
        actual = tuple(
            item.text for item in metadata.findall("Item") if item.get("role") == "description"
        )
    if array.shape != (256, 256, len(names)) or array.dtype != np.float32 or actual != names:
        raise ValueError(f"AF test channel schema mismatch: {path}")
    return array


def scan(root: Path, ids: list[str]) -> dict:
    names = (*VIIRS_BANDS, *AUX_BANDS, *EXTRA_BANDS)
    samples = {name: [] for name in names}
    nonfinite = {name: 0 for name in (*VIIRS_BANDS, *AUX_BANDS)}
    minima = {name: float("inf") for name in names}
    maxima = {name: float("-inf") for name in names}
    landcover_codes = set()
    valid_pixels = 0
    valid_fractions = []
    aux_nonfinite_on_valid = 0
    for cid in ids:
        viirs = _read_tiff(root / "viirs" / f"{cid}_VIIRS_I1-I5.tif", VIIRS_BANDS)
        aux = _read_tiff(root / "aux" / f"{cid}_AUX.tif", AUX_BANDS)
        chip = Chip(cid, viirs, aux, None)
        valid = valid_mask(chip)
        valid_pixels += int(valid.sum())
        valid_fractions.append(float(valid.mean()))
        aux_nonfinite_on_valid += int((~np.isfinite(aux) & valid[..., None]).sum())
        for index, name in enumerate(VIIRS_BANDS):
            nonfinite[name] += int((~np.isfinite(viirs[..., index])).sum())
        for index, name in enumerate(AUX_BANDS):
            nonfinite[name] += int((~np.isfinite(aux[..., index])).sum())
        i4 = np.nan_to_num(viirs[..., 3], nan=0.0, posinf=0.0, neginf=0.0)
        i5 = np.nan_to_num(viirs[..., 4], nan=0.0, posinf=0.0, neginf=0.0)
        layers = [
            *(viirs[..., index] for index in range(len(VIIRS_BANDS))),
            *(aux[..., index] for index in range(len(AUX_BANDS))),
            i4 - i5,
            i4 - median_filter(i4, size=7, mode="reflect"),
        ]
        for name, layer in zip(names, layers, strict=True):
            good = layer[valid & np.isfinite(layer)]
            if good.size:
                minima[name] = min(minima[name], float(good.min()))
                maxima[name] = max(maxima[name], float(good.max()))
            sampled = layer[::16, ::16][valid[::16, ::16]]
            sampled = sampled[np.isfinite(sampled)]
            if sampled.size:
                samples[name].append(sampled.astype(np.float32))
        landcover_codes.update(
            float(value) for value in np.unique(aux[..., 0][valid & np.isfinite(aux[..., 0])])
        )
    quantiles = {}
    for name in names:
        values = np.concatenate(samples[name]) if samples[name] else np.array([])
        quantiles[name] = {
            "sample_count": int(values.size),
            "min": minima[name] if values.size else None,
            "p05": float(np.quantile(values, 0.05)) if values.size else None,
            "p25": float(np.quantile(values, 0.25)) if values.size else None,
            "median": float(np.median(values)) if values.size else None,
            "p75": float(np.quantile(values, 0.75)) if values.size else None,
            "p95": float(np.quantile(values, 0.95)) if values.size else None,
            "max": maxima[name] if values.size else None,
        }
    return {
        "chips": len(ids),
        "valid_pixels": valid_pixels,
        "valid_fraction": valid_pixels / (len(ids) * 256 * 256),
        "valid_fraction_min": min(valid_fractions),
        "valid_fraction_max": max(valid_fractions),
        "nonfinite_by_channel": nonfinite,
        "aux_nonfinite_on_valid": aux_nonfinite_on_valid,
        "landcover_codes": sorted(landcover_codes),
        "channels": quantiles,
    }


def audit() -> dict:
    meta, sample, af_ids, bs_ids = template_ids()
    train_ids = load_meta()["chip_id"].tolist()
    train = scan(TRAIN_ROOT, train_ids)
    test = scan(TEST_ROOT / "af", af_ids)
    shift = {}
    for name in train["channels"]:
        old = train["channels"][name]
        new = test["channels"][name]
        shift[name] = {
            "train_median": old["median"],
            "test_median": new["median"],
            "median_delta": new["median"] - old["median"],
            "train_p05": old["p05"],
            "test_p05": new["p05"],
            "train_p95": old["p95"],
            "test_p95": new["p95"],
        }
    actual = meta.set_index("chip_id").loc[af_ids, "valid_frac"].to_numpy()
    result = {
        "test_root": str(TEST_ROOT),
        "af_chips": len(af_ids),
        "bs_chips": len(bs_ids),
        "sample_rows": len(sample),
        "sample_pairs_exact": True,
        "test_meta_columns": list(meta.columns),
        "test_meta_valid_fraction_median": float(np.median(actual)),
        "test_meta_cloud_fraction_available": bool(
            meta.loc[meta.kind == "af", "cloud_frac"].notna().any()
        ),
        "train": train,
        "test": test,
        "new_landcover_codes": sorted(set(test["landcover_codes"]) - set(train["landcover_codes"])),
        "shift": shift,
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "af_test_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def calibrate() -> dict:
    train_ids = set(load_meta()["chip_id"])
    seen = []
    positive = np.zeros(1001, dtype=np.int64)
    negative = np.zeros(1001, dtype=np.int64)
    sources = []
    for fold in range(1, 4):
        path = EXPERIMENTS / f"af_cv_lgbm_{CV_TAG}_{fold}.npz"
        sources.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        with np.load(path) as data:
            ids = data["ids"].tolist()
            seen.extend(ids)
            for index in range(len(ids)):
                probabilities = data[f"proba_{index}"]
                truth = data[f"true_{index}"]
                valid = data[f"valid_{index}"]
                if probabilities.shape != (256, 256) or truth.shape != valid.shape:
                    raise ValueError("OOF probability map shape mismatch")
                if not np.isfinite(probabilities[valid]).all():
                    raise ValueError("nonfinite OOF probability")
                bins = np.clip((probabilities[valid] * 1000).astype(np.int32), 0, 1000)
                positive += np.bincount(bins[truth[valid]], minlength=1001)
                negative += np.bincount(bins[~truth[valid]], minlength=1001)
    if len(seen) != len(train_ids) or set(seen) != train_ids:
        raise ValueError("OOF maps do not cover each train chip exactly once")
    tp = np.cumsum(positive[::-1])[::-1]
    fp = np.cumsum(negative[::-1])[::-1]
    fn = positive.sum() - tp
    denominator = 2 * tp + fp + fn
    f1 = np.divide(2 * tp, denominator, out=np.zeros_like(tp, dtype=float), where=denominator > 0)
    selected = int(np.argmax(f1[50:1000]) + 50)
    threshold = selected / 1000
    result = {
        "method": "pooled out-of-fold train probabilities; global F1 maximum on 0.001 grid",
        "validity": "VIIRS valid=1, finite I4/I5, mask!=255; missing I1-I3 imputed by features",
        "threshold": threshold,
        "oof_precision": float(tp[selected] / (tp[selected] + fp[selected])),
        "oof_recall": float(tp[selected] / (tp[selected] + fn[selected])),
        "oof_f1": float(f1[selected]),
        "oof_valid_pixels": int(positive.sum() + negative.sum()),
        "oof_positive_pixels": int(positive.sum()),
        "train_chips": len(seen),
        "train_ids_sha256": hashlib.sha256("\n".join(sorted(seen)).encode()).hexdigest(),
        "sources": sources,
    }
    CALIBRATION.write_text(json.dumps(result, indent=2) + "\n")
    return result


def full_train() -> dict:
    from af_final_model import mine_hard_negatives
    from kroma_ml.af_model import sample_training_pixels
    from lightgbm import LGBMClassifier

    calibration = json.loads(CALIBRATION.read_text())
    meta = load_meta()
    ids = meta["chip_id"].tolist()
    checksum = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()
    if checksum != calibration["train_ids_sha256"]:
        raise ValueError("full train IDs differ from frozen OOF calibration")
    index = feature_indices(*FEATURE_GROUPS)
    names = tuple(FEATURE_NAMES[position] for position in index)
    if len(index) != 39:
        raise ValueError("final AF feature schema must contain 39 channels")
    started = time.perf_counter()
    negatives = mine_hard_negatives(ids, meta, index)
    features, labels, _ = sample_training_pixels(
        ids, neg_per_chip=400, seed=42, extra_negatives=negatives, feature_indices=index
    )
    model = LGBMClassifier(
        n_estimators=300,
        num_leaves=31,
        learning_rate=0.05,
        class_weight="balanced",
        random_state=42,
        verbosity=-1,
    )
    model.fit(features, labels)
    bundle = {
        "model": model,
        "feature_indices": index,
        "feature_names": names,
        "threshold": calibration["threshold"],
        "train_ids_sha256": checksum,
        "calibration": str(CALIBRATION),
        "training_samples": int(len(labels)),
        "training_positive_pixels": int(labels.sum()),
        "hard_negative_chips": len(negatives),
    }
    FINAL_MODEL.parent.mkdir(parents=True, exist_ok=True)
    temporary = FINAL_MODEL.with_suffix(".joblib.tmp")
    joblib.dump(bundle, temporary)
    reloaded = joblib.load(temporary)
    if (
        tuple(reloaded["feature_names"]) != names
        or reloaded["threshold"] != calibration["threshold"]
    ):
        raise ValueError("saved full-train AF artifact failed schema check")
    temporary.replace(FINAL_MODEL)
    result = {
        "artifact": str(FINAL_MODEL),
        "artifact_sha256": hashlib.sha256(FINAL_MODEL.read_bytes()).hexdigest(),
        "threshold": calibration["threshold"],
        "train_chips": len(ids),
        "training_samples": int(len(labels)),
        "training_positive_pixels": int(labels.sum()),
        "hard_negative_chips": len(negatives),
        "feature_names": names,
        "runtime_seconds": round(time.perf_counter() - started, 2),
    }
    (EXPERIMENTS / "af_fulltrain_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def encode_rle(mask: np.ndarray) -> str:
    if mask.shape != (256, 256) or not np.isin(mask, (0, 1)).all():
        raise ValueError("AF mask must be binary 256x256")
    flat = mask.astype(np.uint8).ravel(order="C")
    edges = np.flatnonzero(np.diff(np.pad(flat, (1, 1)))) + 1
    return " ".join(
        str(number)
        for start, end in zip(edges[::2], edges[1::2], strict=True)
        for number in (int(start), int(end - start))
    )


def decode_rle(value: str, shape: tuple[int, int] = (256, 256)) -> np.ndarray:
    if not isinstance(value, str) or value.lower() == "nan":
        raise ValueError("RLE must be a string, with empty predictions encoded as empty string")
    mask = np.zeros(shape[0] * shape[1], dtype=np.uint8)
    if not value.strip():
        return mask.reshape(shape)
    numbers = value.split()
    if len(numbers) % 2:
        raise ValueError("RLE must contain start-length pairs")
    last_end = 0
    for start_text, length_text in zip(numbers[::2], numbers[1::2], strict=True):
        start, length = int(start_text), int(length_text)
        if start <= last_end or start < 1 or length < 1 or start + length - 1 > mask.size:
            raise ValueError("RLE run is overlapping or outside the mask")
        mask[start - 1 : start - 1 + length] = 1
        last_end = start + length - 1
    return mask.reshape(shape)


def validate_af_artifact(path: Path = AF_SUBMISSION) -> dict:
    _, sample, af_ids, _ = template_ids()
    rows = pd.read_csv(path, keep_default_na=False)
    if list(rows.columns) != ["chip_id", "class_id", "rle"]:
        raise ValueError("AF submission columns do not match the official template")
    if len(rows) != len(af_ids) or rows.chip_id.duplicated().any():
        raise ValueError("AF submission has missing or duplicate chip IDs")
    if set(rows.chip_id) != set(af_ids) or not (rows.class_id == 1).all():
        raise ValueError("AF submission pairs do not match official AF sample rows")
    expected_order = sample.loc[sample.chip_id.isin(af_ids), "chip_id"].tolist()
    if rows.chip_id.tolist() != expected_order:
        raise ValueError("AF submission row order differs from the template")
    pixels = 0
    for value in rows.rle:
        pixels += int(decode_rle(value).sum())
    return {"rows": len(rows), "decoded_positive_pixels": pixels, "rle_validated": True}


def run_test(warm_runs: int = 2) -> dict:
    _, _, af_ids, _ = template_ids()
    bundle = joblib.load(FINAL_MODEL)
    index = feature_indices(*FEATURE_GROUPS)
    if not np.array_equal(bundle["feature_indices"], index):
        raise ValueError("final AF model feature order differs from code")
    if tuple(bundle["feature_names"]) != tuple(FEATURE_NAMES[position] for position in index):
        raise ValueError("final AF model feature names differ from code")
    threshold = float(bundle["threshold"])
    model = bundle["model"]
    ARTIFACTS.mkdir(exist_ok=True)
    runs = []
    first_rows = []
    first_chips = []
    probability_samples = []
    run_hashes = []
    peak_rss_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for run_number in range(warm_runs + 1):
        started = time.perf_counter()
        timings = {key: 0.0 for key in ("read", "features", "predict", "threshold", "rle")}
        per_chip = []
        digest = hashlib.sha256()
        for cid in af_ids:
            chip_start = time.perf_counter()
            t = time.perf_counter()
            chip = load_chip(cid, root=str(TEST_ROOT / "af"), with_mask=False)
            timings["read"] += time.perf_counter() - t
            t = time.perf_counter()
            stack = chip_feature_stack(chip)
            timings["features"] += time.perf_counter() - t
            t = time.perf_counter()
            probability = model.predict_proba(stack.reshape(-1, stack.shape[-1])[:, index])[
                :, 1
            ].reshape(256, 256)
            timings["predict"] += time.perf_counter() - t
            t = time.perf_counter()
            valid = valid_mask(chip)
            mask = ((probability >= threshold) & valid).astype(np.uint8)
            timings["threshold"] += time.perf_counter() - t
            t = time.perf_counter()
            rle = encode_rle(mask)
            if not np.array_equal(decode_rle(rle), mask):
                raise ValueError(f"AF RLE roundtrip failed for {cid}")
            timings["rle"] += time.perf_counter() - t
            digest.update(cid.encode())
            digest.update(mask.tobytes())
            per_chip.append((time.perf_counter() - chip_start) * 1000)
            if run_number == 0:
                usable = probability[valid]
                if not np.isfinite(usable).all() or (usable < 0).any() or (usable > 1).any():
                    raise ValueError(f"invalid AF probabilities for {cid}")
                first_rows.append((cid, 1, rle))
                physics = physics_predict(chip).astype(bool)
                chosen = mask.astype(bool)
                first_chips.append(
                    {
                        "chip_id": cid,
                        "positive_pixels": int(chosen.sum()),
                        "valid_pixels": int(valid.sum()),
                        "max_probability": float(usable.max()) if usable.size else None,
                        "mean_probability": float(usable.mean()) if usable.size else None,
                        "runtime_ms": per_chip[-1],
                        "physics_positive_pixels": int(physics.sum()),
                        "intersection_physics": int((chosen & physics).sum()),
                        "lightgbm_only": int((chosen & ~physics).sum()),
                        "physics_only": int((physics & ~chosen).sum()),
                    }
                )
                probability_samples.append(usable[::16].astype(np.float32))
        run_hashes.append(digest.hexdigest())
        runs.append(
            {
                "kind": "cold" if run_number == 0 else "warm",
                "total_seconds": round(time.perf_counter() - started, 3),
                "mean_ms_per_chip": round(statistics.mean(per_chip), 3),
                "median_ms_per_chip": round(statistics.median(per_chip), 3),
                "p95_ms_per_chip": round(float(np.quantile(per_chip, 0.95)), 3),
                "stage_seconds": {key: round(value, 3) for key, value in timings.items()},
            }
        )
        print(f"{runs[-1]['kind']} run {run_number}: {runs[-1]['total_seconds']} s", flush=True)
    if len(set(run_hashes)) != 1:
        raise ValueError("AF test predictions differ between repeated runs")
    frame = pd.DataFrame(first_rows, columns=["chip_id", "class_id", "rle"])
    frame.to_csv(AF_SUBMISSION, index=False)
    validated = validate_af_artifact()
    chips = pd.DataFrame(first_chips)
    chips.to_csv(ARTIFACTS / "af_test_chips.csv", index=False)
    positives = chips.loc[chips.positive_pixels > 0, "positive_pixels"]
    probability_values = np.concatenate(probability_samples)
    result = {
        "model": str(FINAL_MODEL),
        "model_sha256": hashlib.sha256(FINAL_MODEL.read_bytes()).hexdigest(),
        "threshold": threshold,
        "af_chips": len(af_ids),
        "positive_chips": int((chips.positive_pixels > 0).sum()),
        "zero_chips": int((chips.positive_pixels == 0).sum()),
        "total_positive_pixels": int(chips.positive_pixels.sum()),
        "positive_fraction_of_valid": float(chips.positive_pixels.sum() / chips.valid_pixels.sum()),
        "positive_fraction_of_all": float(chips.positive_pixels.sum() / (len(chips) * 256 * 256)),
        "median_pixels_per_positive_chip": float(positives.median()) if len(positives) else 0.0,
        "max_pixels_per_chip": int(chips.positive_pixels.max()),
        "valid_fraction": float(chips.valid_pixels.sum() / (len(chips) * 256 * 256)),
        "probability_quantiles_valid_sample": {
            label: float(np.quantile(probability_values, quantile))
            for label, quantile in (
                ("p05", 0.05),
                ("p25", 0.25),
                ("median", 0.5),
                ("p75", 0.75),
                ("p95", 0.95),
                ("p99", 0.99),
            )
        },
        "physics": {
            key: int(chips[key].sum())
            for key in (
                "physics_positive_pixels",
                "intersection_physics",
                "lightgbm_only",
                "physics_only",
            )
        },
        "runs": runs,
        "deterministic_sha256": run_hashes[0],
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_rss_method": "resource.getrusage(RUSAGE_SELF).ru_maxrss on Darwin",
        "peak_rss_start_bytes": peak_rss_start,
        "submission": str(AF_SUBMISSION),
        "submission_validation": validated,
    }
    (ARTIFACTS / "af_test_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def diagnostic_unet() -> dict:
    from kroma_ml.af_unet import AFUNetPredictor

    _, _, af_ids, _ = template_ids()
    rows = pd.read_csv(AF_SUBMISSION, keep_default_na=False).set_index("chip_id")
    predictor = AFUNetPredictor(str(EXPERIMENTS / "af_unet_best.pt"), device="cpu")
    counts = {"both": 0, "lightgbm_only": 0, "resunet_only": 0, "neither": 0}
    for cid in af_ids:
        chip = load_chip(cid, root=str(TEST_ROOT / "af"), with_mask=False)
        lightgbm = decode_rle(rows.loc[cid, "rle"]).astype(bool)
        resunet = predictor.predict_chip(chip).astype(bool)
        counts["both"] += int((lightgbm & resunet).sum())
        counts["lightgbm_only"] += int((lightgbm & ~resunet).sum())
        counts["resunet_only"] += int((~lightgbm & resunet).sum())
        counts["neither"] += int((~lightgbm & ~resunet).sum())
    (ARTIFACTS / "af_test_unet_diagnostic.json").write_text(json.dumps(counts, indent=2) + "\n")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("audit", "calibrate", "train", "infer", "validate", "unet-diagnostic")
    )
    parser.add_argument("--warm-runs", type=int, default=2)
    args = parser.parse_args()
    actions = {
        "audit": audit,
        "calibrate": calibrate,
        "train": full_train,
        "infer": lambda: run_test(args.warm_runs),
        "validate": validate_af_artifact,
        "unet-diagnostic": diagnostic_unet,
    }
    print(json.dumps(actions[args.mode](), indent=2), flush=True)


if __name__ == "__main__":
    main()
