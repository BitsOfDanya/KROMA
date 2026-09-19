import numpy as np
import torch
from kroma_ml.bs_crop import (
    LC_NAMES,
    REFL_NAMES,
    CropDataset,
    RawChip,
    Stats,
    build_channels,
    choose_crop_origin,
    geometric,
)
from kroma_ml.bs_losses import OHEMLoss


def make_raw(seed: int = 0, size: int = 64) -> RawChip:
    rng = np.random.default_rng(seed)
    refl = rng.uniform(0.02, 0.5, size=(8, size, size)).astype(np.float32)
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[10:20, 30:40] = 1
    mask[40:50, 5:15] = 2
    lc = rng.choice([10, 30, 40, 50, 80], size=(size, size)).astype(np.int16)
    scl = np.full((size, size), 4, dtype=np.uint8)
    scl[0:5, 0:5] = 9
    scl[60:, 60:] = 0
    return RawChip("x", refl, scl, scl.copy(), lc, mask)


def stats_for(names: tuple[str, ...]) -> Stats:
    return Stats(names, np.zeros(len(names), np.float32), np.ones(len(names), np.float32))


def test_crop_origin_bounds_and_target_not_always_centred() -> None:
    raw = make_raw()
    rng = np.random.default_rng(1)
    offsets = []
    for mode in ("random", "class1", "burn"):
        for _ in range(200):
            oy, ox = choose_crop_origin(raw.mask, mode, 32, rng)
            assert 0 <= oy <= 32 and 0 <= ox <= 32
            if mode == "class1":
                crop = raw.mask[oy : oy + 32, ox : ox + 32]
                assert (crop == 1).any()
                ys, xs = np.nonzero(crop == 1)
                offsets.append((ys.mean(), xs.mean()))
    assert np.std([o[0] for o in offsets]) > 2 and np.std([o[1] for o in offsets]) > 2


def test_geometric_transform_is_identical_across_modalities() -> None:
    raw = make_raw()
    for k in range(4):
        for flip in (False, True):
            refl, mask, lc = geometric([raw.refl, raw.mask, raw.landcover], k, flip)
            expected = np.rot90(raw.mask, k)
            expected = expected[:, ::-1] if flip else expected
            assert np.array_equal(mask, expected)
            assert np.array_equal(refl[3] > 0.25, geometric([raw.refl[3]], k, flip)[0] > 0.25)
            assert lc.dtype == raw.landcover.dtype
            assert set(np.unique(lc)) <= set(np.unique(raw.landcover))


def test_dataset_targets_valid_and_categorical_channels_binary() -> None:
    raw = make_raw()
    names = (*REFL_NAMES, "dnbr12", "rdnbr12", *LC_NAMES, "q_cloud", "q_clear")
    ds = CropDataset([raw], stats_for(names), crop=32, geom_aug=True, brightness_p=1.0, length=20)
    for i in range(20):
        x, y = ds[i]
        assert x.shape == (len(names), 32, 32) and y.shape == (32, 32)
        assert set(y.unique().tolist()) <= {0, 1, 2, 3, 255}
        lc = x[names.index("lc_forest") : names.index("lc_forest") + 5]
        assert torch.equal(lc.sum(0), torch.ones(32, 32))
        assert torch.isfinite(x).all()


def test_scl_ignore_strategies_differ_on_cloud_only() -> None:
    raw = make_raw()
    strict = CropDataset([raw], stats_for(REFL_NAMES), scl_ignore="strict", geom_aug=False)
    true = CropDataset([raw], stats_for(REFL_NAMES), scl_ignore="true", geom_aug=False)
    assert (strict.targets[0] == 255).sum() > (true.targets[0] == 255).sum() > 0
    assert (true.targets[0][0:5, 0:5] != 255).all()


def test_brightness_uses_one_factor_for_pre_and_post_and_indices_are_recomputed() -> None:
    raw = make_raw()
    names = (*REFL_NAMES, "dnbr12")
    ds = CropDataset(
        [raw], stats_for(names), geom_aug=False, brightness_p=1.0, scl_ignore="true", length=1
    )
    x, _ = ds[0]
    factors = x[:8].numpy() / raw.refl
    assert np.allclose(factors, factors[0, 0, 0], rtol=1e-4)
    assert 0.95 <= factors[0, 0, 0] <= 1.05
    expected = build_channels(
        raw.refl * factors[0, 0, 0], raw.landcover, raw.scl_pre, raw.scl_post, ("dnbr12",)
    )[0]
    assert np.allclose(x[8].numpy(), expected, atol=1e-5)


def test_rdnbr_finite_when_nbr_is_zero() -> None:
    refl = np.full((8, 8, 8), 0.3, dtype=np.float32)
    lc = np.zeros((8, 8), np.int16)
    scl = np.full((8, 8), 4, np.uint8)
    out = build_channels(refl, lc, scl, scl, ("rdnbr", "rdnbr12"))
    assert np.isfinite(out).all() and np.abs(out).max() <= 1.0


def test_ohem_ignores_ignored_pixels_and_keeps_hardest() -> None:
    target = torch.zeros(1, 4, 4, dtype=torch.long)
    target[0, 0, :] = 255
    logits = torch.zeros(1, 4, 4, 4)
    logits[0, 0, 1:, :] = 5.0
    logits[0, 0, 3, 3] = -5.0
    full = OHEMLoss(keep_ratio=1.0)(logits, target)
    hard = OHEMLoss(keep_ratio=0.1)(logits, target)
    assert hard > full
    assert torch.isfinite(OHEMLoss(0.4)(logits, torch.full((1, 4, 4), 255)))


def test_dual_head_output_contract_and_severity_only_on_burn() -> None:
    from kroma_ml.bs_losses import DualHeadLoss
    from kroma_ml.bs_model import DualHeadAttentionUNet, dual_to_class_logits

    model = DualHeadAttentionUNet(in_channels=3, base=4).eval()
    out = model(torch.zeros(1, 3, 32, 32))
    assert out.shape == (1, 4, 32, 32)
    logits4 = dual_to_class_logits(out)
    assert logits4.shape == (1, 4, 32, 32)
    assert torch.allclose(logits4.exp().sum(1), torch.ones(1, 32, 32), atol=1e-5)

    target = torch.zeros(1, 32, 32, dtype=torch.long)
    target[0, 4:8, 4:8] = 2
    target[0, 0, 0] = 255
    base = out.clone().detach()
    a = DualHeadLoss()(base, target)
    changed = base.clone()
    changed[:, 1:, 10:30, 10:30] += 7.0
    assert torch.allclose(
        a, DualHeadLoss()(changed, target) - (DualHeadLoss()(changed, target) - a)
    )
    ordinal = DualHeadLoss(ordinal_weight=0.5)(base, target)
    assert ordinal > a and torch.isfinite(ordinal)
    all_ignored = torch.full((1, 32, 32), 255, dtype=torch.long)
    assert torch.isfinite(DualHeadLoss(0.1)(base, all_ignored))


def test_mine_points_selects_confident_errors_only() -> None:
    from kroma_ml.bs_crop import mine_points

    mask = np.zeros((16, 16), dtype=np.uint8)
    mask[2:6, 2:6] = 1
    logits = np.zeros((4, 16, 16), dtype=np.float32)
    logits[0] = 5.0
    logits[1, 10:12, 10:12] = 9.0
    logits[1, 3:5, 3:5] = 20.0
    valid = np.ones((16, 16), dtype=bool)
    valid[10, 10] = False
    pools = mine_points(mask, logits, valid)
    neg = set(zip(*[a.tolist() for a in pools["hardneg"]], strict=True))
    pos = set(zip(*[a.tolist() for a in pools["hardpos"]], strict=True))
    assert neg == {(10, 11), (11, 10), (11, 11)}
    expected = {(y, x) for y in range(2, 6) for x in range(2, 6)} - {(3, 3), (3, 4), (4, 3), (4, 4)}
    assert pos == expected


def test_boundary01_points_lie_between_class0_and_class1() -> None:
    from kroma_ml.bs_crop import boundary01_points

    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[5:15, 5:15] = 1
    mask[8:12, 8:12] = 2
    ys, xs = boundary01_points(mask, width=1)
    assert len(ys) > 0
    assert (mask[ys, xs] < 2).all()
    inner = (ys > 6) & (ys < 13) & (xs > 6) & (xs < 13)
    assert not inner.any()


def test_dataset_pool_modes_stay_in_bounds_and_target_pixel_is_included() -> None:
    from kroma_ml.bs_crop import MODES, boundary01_points

    raw = make_raw()
    pts = boundary01_points(raw.mask)
    hard = (np.array([60, 61]), np.array([2, 3]))
    pools = {"hardneg": [hard], "boundary01": [pts], "hardpos": [None]}
    ds = CropDataset(
        [raw],
        stats_for(REFL_NAMES),
        crop=32,
        mix=(0.0, 0.0, 0.0, 0.5, 0.5),
        scl_ignore="true",
        geom_aug=False,
        pools=pools,
        length=60,
    )
    assert len(ds.mix) == len(MODES)
    for i in range(60):
        x, y = ds[i]
        assert x.shape[-2:] == (32, 32) and y.shape == (32, 32)


def test_empty_pool_falls_back_to_random_crop() -> None:
    raw = make_raw()
    ds = CropDataset(
        [raw],
        stats_for(REFL_NAMES),
        crop=32,
        mix=(0.0, 0.0, 0.0, 1.0, 0.0),
        pools={"hardneg": [None]},
        length=5,
    )
    for i in range(5):
        assert ds[i][0].shape[-2:] == (32, 32)
