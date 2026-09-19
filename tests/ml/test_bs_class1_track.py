import numpy as np
import pandas as pd
import pytest
import torch
from kroma_ml.af_split import group_key
from kroma_ml.bs_crop import IGNORE_INDEX, RawChip
from kroma_ml.bs_cv import (
    confusion,
    evaluate_scenes,
    fold_ids,
    load_predictions,
    metrics_from_confusion,
    save_predictions,
    valid_mask,
)
from kroma_ml.bs_fast_models import build_model
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.bs_physics import (
    Hist1D,
    Hist2D,
    bs_from_confusion,
    fit_gated,
    fit_thresholds_1d,
    gated_classes,
    spectral_indices,
    threshold_classes,
)
from kroma_ml.bs_sampling import (
    ChipPools,
    TrackCropDataset,
    attach_hard_pool,
    boundary_mask,
    build_pools,
    crop_class1_share,
    hard_pixels,
    parse_mix,
    track_stats,
)
from kroma_ml.bs_track_losses import TrackLoss, lovasz_softmax, soft_dice, soft_tversky


def refl_from(pre: tuple[float, ...], post: tuple[float, ...], size: int = 4) -> np.ndarray:
    return np.stack([np.full((size, size), v, np.float32) for v in (*pre, *post)])


def make_raw(chip_id: str = "c", size: int = 96, seed: int = 0) -> RawChip:
    rng = np.random.default_rng(seed)
    refl = rng.uniform(0.02, 0.4, size=(8, size, size)).astype(np.float32)
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[20:50, 20:50] = 1
    mask[30:40, 30:40] = 2
    mask[70:80, 70:80] = 3
    scl = np.full((size, size), 4, dtype=np.uint8)
    scl[0:6, 0:6] = 10
    scl[90:, 90:] = 1
    lc = np.full((size, size), 40, dtype=np.int16)
    return RawChip(chip_id, refl, scl, scl.copy(), lc, mask)


def test_physics_indices_match_textbook_formulas() -> None:
    pre = (0.05, 0.30, 0.20, 0.10)
    post = (0.08, 0.15, 0.25, 0.20)
    idx = spectral_indices(refl_from(pre, post))
    nbr_pre = (0.30 - 0.10) / (0.30 + 0.10)
    nbr_post = (0.15 - 0.20) / (0.15 + 0.20)
    ndvi_pre = (0.30 - 0.05) / (0.30 + 0.05)
    ndvi_post = (0.15 - 0.08) / (0.15 + 0.08)
    assert idx["nbr_pre"][0, 0] == pytest.approx(nbr_pre, abs=1e-6)
    assert idx["nbr_post"][0, 0] == pytest.approx(nbr_post, abs=1e-6)
    assert idx["dnbr"][0, 0] == pytest.approx(nbr_pre - nbr_post, abs=1e-6)
    assert idx["dndvi"][0, 0] == pytest.approx(ndvi_pre - ndvi_post, abs=1e-6)
    assert idx["d_nir"][0, 0] == pytest.approx(0.15 - 0.30, abs=1e-6)
    assert idx["d_swir2"][0, 0] == pytest.approx(0.20 - 0.10, abs=1e-6)


def test_rdnbr_uses_b12_and_legacy_uses_b11() -> None:
    pre = (0.05, 0.30, 0.25, 0.10)
    post = (0.08, 0.15, 0.25, 0.20)
    idx = spectral_indices(refl_from(pre, post))
    nbr12_pre = (0.30 - 0.10) / 0.40
    dnbr12 = nbr12_pre - (0.15 - 0.20) / 0.35
    nbr11_pre = (0.30 - 0.25) / 0.55
    dnbr11 = nbr11_pre - (0.15 - 0.25) / 0.40
    assert idx["rdnbr"][0, 0] == pytest.approx(dnbr12 / (np.sqrt(nbr12_pre) + 1e-2), abs=1e-5)
    assert idx["rdnbr_b11"][0, 0] == pytest.approx(dnbr11 / (np.sqrt(nbr11_pre) + 1e-2), abs=1e-5)
    assert abs(idx["rdnbr"][0, 0] - idx["rdnbr_b11"][0, 0]) > 0.1


def test_indices_are_finite_on_zero_reflectance() -> None:
    idx = spectral_indices(np.zeros((8, 3, 3), np.float32))
    assert all(np.isfinite(v).all() for v in idx.values())


def test_threshold_fit_recovers_generating_thresholds() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(-0.2, 1.0, 200_000)
    labels = threshold_classes(x, (0.1, 0.3, 0.6))
    hist = Hist1D.empty(-0.5, 1.5, 400)
    hist.add(x, labels)
    t, score = fit_thresholds_1d(hist)
    assert np.allclose(t, (0.1, 0.3, 0.6), atol=0.006)
    assert score == pytest.approx(0.65, abs=1e-3)


def test_gated_fit_recovers_gate_and_severity() -> None:
    rng = np.random.default_rng(1)
    gate, sev = rng.uniform(-0.5, 1.5, 100_000), rng.uniform(-0.5, 1.5, 100_000)
    labels = gated_classes(gate, 0.2, sev, (0.4, 0.9))
    hist = Hist2D.empty((-0.5, 1.5, 80), (-0.5, 1.5, 80))
    hist.add(gate, sev, labels)
    t, score = fit_gated(hist)
    assert np.allclose(t, (0.2, 0.4, 0.9), atol=0.03)
    assert score == pytest.approx(0.65, abs=1e-3)


def test_confusion_metrics_equal_official_evaluator() -> None:
    rng = np.random.default_rng(2)
    preds = [rng.integers(0, 4, (32, 32)) for _ in range(3)]
    trues = [rng.integers(0, 4, (32, 32)) for _ in range(3)]
    valids = [rng.random((32, 32)) > 0.2 for _ in range(3)]
    official = evaluate_predictions(preds, trues, valids)
    ours = evaluate_scenes(preds, trues, valids)
    cm = sum(confusion(p, t, v) for p, t, v in zip(preds, trues, valids, strict=True))
    assert ours["bs_score"] == pytest.approx(official["bs_score"], abs=1e-12)
    assert np.allclose(ours["iou_per_class"], official["iou_per_class"])
    assert float(bs_from_confusion(cm)) == pytest.approx(official["bs_score"], abs=1e-12)


def test_class1_precision_recall_from_confusion() -> None:
    cm = np.array([[90, 10, 0, 0], [5, 15, 0, 0], [0, 0, 10, 0], [0, 0, 0, 10]])
    m = metrics_from_confusion(cm)
    assert m["precision_per_class"][1] == pytest.approx(15 / 25)
    assert m["recall_per_class"][1] == pytest.approx(15 / 20)
    assert m["iou_per_class"][1] == pytest.approx(15 / 30)


def test_scl_mask_policies() -> None:
    raw = make_raw()
    raw.refl[:, 50, 50] = 0.0
    strict = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "strict")
    true = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "true")
    none = valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "none")
    assert not strict[0, 0] and true[0, 0] and none[0, 0]
    assert not strict[95, 95] and not true[95, 95]
    assert not none[50, 50] and true[50, 50]
    assert strict.sum() < true.sum()
    with pytest.raises(ValueError):
        valid_mask(raw.scl_pre, raw.scl_post, raw.refl, "loose")


def test_group_folds_do_not_leak() -> None:
    n = 60
    meta = pd.DataFrame(
        {
            "chip_id": [f"c{i}" for i in range(n)],
            "fire_event_id": [f"F{i // 3}" for i in range(n)],
            "x_min": 0,
            "y_min": 0,
            "x_max": 1,
            "y_max": 1,
        }
    )
    groups = dict(zip(meta["chip_id"], group_key(meta), strict=True))
    folds = fold_ids(meta)
    seen = set()
    for train, val in folds:
        assert not set(train) & set(val)
        assert not {groups[c] for c in train} & {groups[c] for c in val}
        seen |= set(val)
    assert seen == set(meta["chip_id"])


def test_class1_crops_always_contain_class1() -> None:
    raw = make_raw()
    pools = {raw.chip_id: build_pools(raw, np.random.default_rng(0))}
    stats = track_stats([raw], ("pre_nir", "post_nir", "dnbr12"), None)
    ds = TrackCropDataset(
        [raw], stats, 32, parse_mix("class1:1"), pools, scl_ignore="true", length=50
    )
    for i in range(50):
        _, target = ds.sample(i)
        assert (target == 1).any()
    assert crop_class1_share(ds, 50)["any_class1"] == 1.0


def test_boundary_pool_and_crops_touch_both_classes() -> None:
    raw = make_raw()
    b01 = boundary_mask(raw.mask, 0, 1, radius=2)
    ys, xs = np.nonzero(b01)
    assert len(ys) > 0
    assert (np.abs(ys - 20) <= 2).any() or (np.abs(ys - 49) <= 2).any()
    pools = {raw.chip_id: build_pools(raw, np.random.default_rng(0))}
    stats = track_stats([raw], ("pre_nir",), None)
    ds = TrackCropDataset([raw], stats, 32, parse_mix("b01:1"), pools, length=200)
    both = [((t == 0).any() and (t == 1).any()) for t in (ds.sample(i)[1] for i in range(200))]
    assert np.mean(both) > 0.9


def test_hard_pixels_and_train_only_pool() -> None:
    mask = np.array([[1, 0], [2, 1]])
    probs = np.zeros((4, 2, 2), np.float32)
    probs[0, 0, 0] = 0.9
    probs[1, 0, 1] = 0.8
    probs[1, 1, 0] = 0.7
    probs[1, 1, 1] = 0.9
    probs[:, :, :] += 0.01
    coords, w = hard_pixels(probs, mask, np.ones((2, 2), bool))
    got = {tuple(c) for c in coords}
    assert got == {(0, 0), (0, 1), (1, 0)}
    assert w.max() == 4.0
    pools = {"a": ChipPools(), "b": ChipPools()}
    rng = np.random.default_rng(0)
    attach_hard_pool(pools, {"a": (coords, w)}, {"a"}, rng)
    assert len(pools["a"].pools["hard"]) == 3
    with pytest.raises(ValueError):
        attach_hard_pool(pools, {"b": (coords, w)}, {"a"}, rng)


def test_prediction_contract_roundtrip(tmp_path) -> None:
    logits = np.random.default_rng(3).normal(size=(2, 4, 512, 512)).astype(np.float32)
    path = tmp_path / "p.npz"
    save_predictions(path, ["a", "b"], logits)
    ids, labels = load_predictions(path)
    assert ids == ["a", "b"]
    assert np.array_equal(labels, logits.astype(np.float16).astype(np.float32).argmax(1))
    np.savez(tmp_path / "bad.npz", ids=np.array(["a"]), logits=np.zeros((1, 3, 512, 512)))
    with pytest.raises(ValueError):
        load_predictions(tmp_path / "bad.npz")
    np.savez(tmp_path / "dup.npz", ids=np.array(["a", "a"]), labels=np.zeros((2, 512, 512)))
    with pytest.raises(ValueError):
        load_predictions(tmp_path / "dup.npz")
    np.savez(tmp_path / "order.npz", ids=np.array(["a"]), labels=np.zeros((1, 512, 512)),
             class_order=np.array(["high", "moderate", "low", "background"]))  # fmt: skip
    with pytest.raises(ValueError):
        load_predictions(tmp_path / "order.npz")


def test_track_losses_are_finite_and_respect_ignore() -> None:
    torch.manual_seed(0)
    target = torch.randint(0, 4, (2, 16, 16))
    target[:, :4] = IGNORE_INDEX
    good = torch.nn.functional.one_hot(target.clamp(max=3), 4).permute(0, 3, 1, 2).float() * 8
    bad = torch.randn(2, 4, 16, 16)
    assert soft_dice(good, target, 1) < soft_dice(bad, target, 1)
    assert soft_tversky(good, target, 1, 0.3, 0.7) < soft_tversky(bad, target, 1, 0.3, 0.7)
    assert lovasz_softmax(good, target) < lovasz_softmax(bad, target)
    for kind in ("ohem", "ohem_dice1", "ohem_tversky1", "ohem_lovasz"):
        loss = TrackLoss(kind)(bad.requires_grad_(), target)
        assert torch.isfinite(loss)
    all_ignored = torch.full((1, 8, 8), IGNORE_INDEX)
    assert torch.isfinite(lovasz_softmax(torch.randn(1, 4, 8, 8), all_ignored))


@pytest.mark.parametrize("name", ["attunet", "segformer_b0", "mobileunet"])
def test_fast_models_keep_resolution(name: str) -> None:
    model = build_model(name, 7).eval()
    with torch.no_grad():
        out = model(torch.randn(1, 7, 64, 64))
    assert out.shape == (1, 4, 64, 64)


def test_organizer_thresholds_match_case_figure6() -> None:
    from pathlib import Path

    from kroma_ml.bs_v004 import GROUP_ORDER, group_map, load_thresholds

    path = (
        Path(__file__).resolve().parents[2] / "research/experiments/bs_v004_physics_thresholds.json"
    )
    th = load_thresholds(path)
    table = dict(zip(GROUP_ORDER, th["table"].tolist(), strict=True))
    assert np.allclose(table["forest_shrub"], (0.10, 0.27, 0.66))
    assert np.allclose(table["grassland"], (0.062, 0.204, 0.386))
    assert np.allclose(table["cropland"], (0.07, 0.177, 0.38))
    assert np.allclose(table["wetland_floodplain"], (0.075, 0.331, 0.677))
    lc = np.array([[10, 20, 30, 40, 90, 50]])
    assert group_map(lc, th).tolist() == [[0, 0, 1, 2, 3, 3]]


def test_organizer_severity_is_landcover_conditional() -> None:
    from pathlib import Path

    from kroma_ml.bs_v004 import load_thresholds, organizer_severity, threshold_map

    path = (
        Path(__file__).resolve().parents[2] / "research/experiments/bs_v004_physics_thresholds.json"
    )
    th = load_thresholds(path)
    lc = np.array([[10, 40, 30, 90]])
    dnbr = np.full((1, 4), 0.20, np.float32)
    sev = organizer_severity(dnbr, threshold_map(lc, th))
    assert sev.tolist() == [[1, 2, 1, 1]]
    assert organizer_severity(np.full((1, 4), 0.05, np.float32), threshold_map(lc, th)).max() == 0


def test_physics_hybrid_never_draws_burn_outside_ml_contour() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research/experiments"))
    from bs_v004_fasttrack import hybrids

    rng = np.random.default_rng(0)
    probs = rng.dirichlet(np.ones(4), size=(16, 16)).transpose(2, 0, 1)
    f = {
        "pred": probs.argmax(0),
        "p1": probs[1], "p2": probs[2], "p3": probs[3], "p_burn": 1 - probs[0],
        "org_sev": np.full((16, 16), 3),
    }  # fmt: skip
    for pred in hybrids(f, np.log(probs)).values():
        assert ((f["pred"] == 0) == (pred == 0)).all()


def test_refine_gate_keeps_confident_severe_pixels() -> None:
    from kroma_ml.bs_v004 import refine_gate

    f = {
        "p_burn": np.array([0.5, 0.5, 0.99]),
        "dist_pred_boundary": np.array([10.0, 10.0, 1.0]),
        "pred": np.array([1, 3, 0]),
        "p2": np.array([0.1, 0.1, 0.0]),
        "p3": np.array([0.1, 0.7, 0.0]),
    }
    assert refine_gate(f, 0.2, 2.0, 0.6).tolist() == [True, False, True]
