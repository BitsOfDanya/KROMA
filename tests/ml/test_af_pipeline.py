import os
import runpy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from kroma_ml.af_data import AF_ROOT, load_chip, load_meta, valid_mask
from kroma_ml.af_features import FEATURE_NAMES, chip_feature_stack, feature_indices
from kroma_ml.af_metrics import confusion, precision_recall_f1
from kroma_ml.af_postprocess import remove_small_components
from kroma_ml.af_split import group_key, train_val_split
from kroma_ml.af_threshold import sweep

pytestmark = pytest.mark.skipif(
    not os.path.isdir(AF_ROOT), reason="official AF dataset not present locally"
)


@pytest.fixture(scope="module")
def meta():
    return load_meta()


@pytest.fixture(scope="module")
def sample_chip():
    return load_chip("AF_tr_000001")


def test_feature_stack_shape_matches_names(sample_chip) -> None:
    stack = chip_feature_stack(sample_chip)
    assert stack.shape == (256, 256, len(FEATURE_NAMES))


def test_feature_stack_has_no_nan_or_inf(sample_chip) -> None:
    stack = chip_feature_stack(sample_chip)
    assert np.isfinite(stack).all()


def test_feature_indices_resolve_known_names() -> None:
    idx = feature_indices("raw", "landcover")
    assert len(idx) == 6
    assert all(0 <= i < len(FEATURE_NAMES) for i in idx)


def test_split_has_no_group_leakage(meta) -> None:
    train_ids, val_ids = train_val_split(meta, val_size=0.2, seed=1)
    groups = group_key(meta)
    by_chip = dict(zip(meta["chip_id"], groups, strict=True))
    train_groups = {by_chip[c] for c in train_ids}
    val_groups = {by_chip[c] for c in val_ids}
    assert train_groups.isdisjoint(val_groups)
    assert set(train_ids).isdisjoint(set(val_ids))


def test_split_is_seed_reproducible(meta) -> None:
    a_train, a_val = train_val_split(meta, seed=7)
    b_train, b_val = train_val_split(meta, seed=7)
    assert list(a_train) == list(b_train)
    assert list(a_val) == list(b_val)


def test_metric_perfect_prediction_is_f1_one() -> None:
    true = np.zeros((4, 4), dtype=bool)
    true[0, 0] = True
    true[1, 1] = True
    counts = confusion(true, true)
    _, _, f1 = precision_recall_f1(counts)
    assert f1 == 1.0


def test_metric_empty_prediction_and_truth_is_zero() -> None:
    pred = np.zeros((4, 4), dtype=bool)
    true = np.zeros((4, 4), dtype=bool)
    counts = confusion(pred, true)
    p, r, f1 = precision_recall_f1(counts)
    assert (p, r, f1) == (0.0, 0.0, 0.0)


def test_metric_respects_valid_mask() -> None:
    pred = np.array([[True, True], [False, False]])
    true = np.array([[True, False], [False, False]])
    valid = np.array([[True, False], [True, True]])
    counts = confusion(pred, true, valid)
    assert counts.tp == 1
    assert counts.fp == 0


def test_threshold_sweep_picks_best_f1() -> None:
    proba = [np.array([0.9, 0.1, 0.6, 0.4])]
    true = [np.array([True, False, True, False])]
    valid = [np.array([True, True, True, True])]
    best_t, best_f1, results = sweep(proba, true, valid, grid=np.array([0.2, 0.5, 0.8]))
    assert best_f1 == pytest.approx(1.0)
    assert best_t == 0.5
    assert set(results.keys()) == {0.2, 0.5, 0.8}


def test_postprocess_binary_output_and_shape() -> None:
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[2, 2] = 1
    mask[4:6, 4:6] = 1
    out = remove_small_components(mask, min_size=3)
    assert out.shape == mask.shape
    assert set(np.unique(out)).issubset({0, 1})
    assert out[2, 2] == 0
    assert out[4, 4] == 1


def test_valid_mask_is_binary_and_matches_shape(sample_chip) -> None:
    valid = valid_mask(sample_chip)
    assert valid.shape == (256, 256)
    assert valid.dtype == bool


def test_valid_mask_keeps_thermal_pixels_when_daylight_bands_are_missing(sample_chip) -> None:
    from kroma_ml.af_data import Chip

    viirs = sample_chip.viirs.copy()
    viirs[..., :3] = np.nan
    chip = Chip("night", viirs, sample_chip.aux, sample_chip.mask)
    valid = valid_mask(chip)
    assert valid.any()
    assert valid[0, 0]
    viirs[0, 0, 3] = np.nan
    assert not valid_mask(Chip("missing_thermal", viirs, sample_chip.aux, sample_chip.mask))[0, 0]


def test_af_predictor_is_deterministic_binary_and_shaped() -> None:
    from kroma_ml.af_infer import DEFAULT_MODEL_PATH

    if not DEFAULT_MODEL_PATH.exists():
        pytest.skip("trained AF model artifact not present locally")
    code = (
        "import numpy as np\n"
        "from kroma_ml.af_infer import AFPredictor\n"
        "from kroma_ml.af_data import load_chip\n"
        "predictor = AFPredictor()\n"
        "chip = load_chip('AF_tr_000001', with_mask=False)\n"
        "first = predictor.predict_chip(chip)\n"
        "second = predictor.predict_chip(chip)\n"
        "assert first.shape == (256, 256) and first.dtype == np.uint8\n"
        "assert set(np.unique(first)).issubset({0, 1})\n"
        "np.testing.assert_array_equal(first, second)\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=30)


def test_unet_forward_shape() -> None:
    import torch
    from kroma_ml.af_unet import SmallUNet

    model = SmallUNet(in_channels=5, base=4)
    x = torch.zeros(2, 5, 64, 64)
    y = model(x)
    assert y.shape == (2, 1, 64, 64)


def test_resunet_forward_shape() -> None:
    import torch
    from kroma_ml.af_unet import SmallUNet

    model = SmallUNet(in_channels=3, base=4, residual=True)
    x = torch.zeros(1, 3, 64, 64)
    y = model(x)
    assert y.shape == (1, 1, 64, 64)


def test_losses_are_finite_and_decrease_toward_perfect_prediction() -> None:
    import torch
    from kroma_ml.af_losses import LOSSES

    targets = torch.zeros(1, 1, 8, 8)
    targets[0, 0, 2:4, 2:4] = 1.0
    valid = torch.ones_like(targets)
    bad_logits = torch.zeros_like(targets)
    good_logits = (targets * 2 - 1) * 10
    for name, fn in LOSSES.items():
        bad = fn(bad_logits, targets, valid).item()
        good = fn(good_logits, targets, valid).item()
        assert np.isfinite(bad)
        assert np.isfinite(good)
        assert good < bad, name


def test_channel_stats_and_normalization_shapes(sample_chip) -> None:
    from kroma_ml.af_features import unet_channel_stack
    from kroma_ml.af_torch_data import ChannelStats, normalize

    names = ("I1", "I2", "I3", "I4", "I5")
    stack = unet_channel_stack(sample_chip, names)
    stats = ChannelStats(
        names=names, mean=np.zeros(5, dtype=np.float32), std=np.ones(5, dtype=np.float32)
    )
    normed = normalize(stack, stats)
    assert normed.shape == stack.shape
    assert np.isfinite(normed).all()


def test_nodata_is_ignored_by_loss_and_metric(sample_chip) -> None:
    import torch
    from kroma_ml.af_data import Chip
    from kroma_ml.af_losses import LOSSES

    mask = np.zeros((256, 256), dtype=np.uint8)
    mask[0, 0] = 255
    mask[1, 1] = 1
    chip = Chip("synthetic", sample_chip.viirs, sample_chip.aux, mask)
    valid = valid_mask(chip)
    assert not valid[0, 0]
    targets = torch.from_numpy((mask == 1).astype(np.float32))[None, None]
    allowed = torch.from_numpy(valid.astype(np.float32))[None, None]
    logits = torch.zeros_like(targets)
    changed = logits.clone()
    changed[0, 0, 0, 0] = 20
    for loss in LOSSES.values():
        assert torch.allclose(loss(logits, targets, allowed), loss(changed, targets, allowed))
    counts = confusion(changed[0, 0].numpy() > 0, mask == 1, valid)
    assert counts.fp == 0


def test_train_stats_skip_landcover_and_valid(monkeypatch) -> None:
    from kroma_ml.af_data import Chip
    from kroma_ml.af_torch_data import compute_channel_stats, normalize

    viirs = np.ones((2, 2, 8), dtype=np.float32)
    aux = np.zeros((2, 2, 5), dtype=np.float32)
    aux[..., 0] = 90
    chip = Chip("train", viirs, aux, np.zeros((2, 2), dtype=np.uint8))
    names = ("I1", "landcover", "valid")
    monkeypatch.setattr("kroma_ml.af_torch_data.load_chip", lambda _: chip)
    monkeypatch.setattr(
        "kroma_ml.af_torch_data.cached_unet_stack",
        lambda *_: np.stack([chip.band(name) for name in names], axis=-1),
    )
    stats = compute_channel_stats(["train"], names)
    np.testing.assert_array_equal(stats.mean, [1, 0, 0])
    np.testing.assert_allclose(stats.std, [1e-4, 1, 1])
    normalized = normalize(np.stack([chip.band(name) for name in names], axis=-1), stats)
    assert np.all(normalized[..., 1] == 0.9)
    assert np.all(normalized[..., 2] == 1)


def test_unet_channel_order_and_eval_are_deterministic(sample_chip) -> None:
    import torch
    from kroma_ml.af_features import UNET_CONFIGS, unet_channel_stack
    from kroma_ml.af_unet import SmallUNet

    for names in UNET_CONFIGS.values():
        stack = unet_channel_stack(sample_chip, names)
        assert stack.shape == (256, 256, len(names))
        np.testing.assert_array_equal(stack[..., 0], np.nan_to_num(sample_chip.band("I1")))
        np.testing.assert_array_equal(stack, unet_channel_stack(sample_chip, names))
    model = SmallUNet(in_channels=5, base=4).eval()
    x = torch.randn(1, 5, 32, 32)
    with torch.no_grad():
        assert torch.equal(model(x), model(x))


def test_saved_unet_validation_uses_af_group_split(meta) -> None:
    path = Path(__file__).resolve().parents[2] / "research/experiments/af_unet_val_probas.npz"
    if not path.exists():
        pytest.skip("saved U-Net validation maps not present")
    _, val_ids = train_val_split(meta)
    with np.load(path) as maps:
        assert list(maps["val_ids"]) == list(val_ids)


def test_saved_unet_checkpoint_reproduces_validation_map() -> None:
    from kroma_ml.af_unet import AFUNetPredictor

    root = Path(__file__).resolve().parents[2] / "research/experiments"
    checkpoint = root / "af_unet_best.pt"
    maps_path = root / "af_unet_val_probas.npz"
    if not checkpoint.exists() or not maps_path.exists():
        pytest.skip("saved U-Net checkpoint and maps not present")
    predictor = AFUNetPredictor(str(checkpoint), device="cpu")
    with np.load(maps_path) as maps:
        chip = load_chip(str(maps["val_ids"][0]))
        probabilities = predictor.predict_chip_proba(chip)
        np.testing.assert_allclose(
            probabilities[maps["valid_0"]], maps["proba_0"][maps["valid_0"]], atol=1e-5
        )
        mask = predictor.predict_chip(chip)
        assert mask.shape == (256, 256)
        assert set(np.unique(mask)).issubset({0, 1})


def test_ensemble_probability_range_and_validation() -> None:
    function = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "research/experiments/af_ensemble.py")
    )["blend_probabilities"]
    result = function(np.array([0.0, 0.8]), np.array([1.0, 0.2]), 0.9)
    np.testing.assert_allclose(result, [0.1, 0.74])
    assert np.all((0 <= result) & (result <= 1))
    with pytest.raises(ValueError):
        function(np.zeros(1), np.zeros(2), 0.5)


def test_cv_histogram_threshold_counts_valid_pixels() -> None:
    function = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "research/experiments/af_group_cv.py")
    )["tune"]
    proba = [np.array([0.9, 0.8, 0.2, 0.1, 0.99])]
    true = [np.array([True, False, True, False, False])]
    valid = [np.array([True, True, True, True, False])]
    result = function(proba, true, valid)
    assert result["precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["recall"] == 1.0
    assert result["f1"] == 0.8
