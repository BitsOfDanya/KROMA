import os

import numpy as np
import pytest
from kroma_ml.bs_data import BS_ROOT, load_chip, load_meta, valid_mask
from kroma_ml.bs_features import BS_CONFIGS, bs_channel_stack
from kroma_ml.bs_losses import BurnSeverityLoss, CombinedLoss
from kroma_ml.bs_metrics import evaluate_predictions
from kroma_ml.submission import decode_rle, encode_rle, multiclass_to_binary_rles, roundtrip_check

pytestmark = pytest.mark.skipif(
    not os.path.isdir(BS_ROOT), reason="official BS dataset not present locally"
)


@pytest.fixture(scope="module")
def sample_chip():
    return load_chip("BS_tr_000002")


def test_meta_has_fire_event_id() -> None:
    meta = load_meta()
    assert meta["fire_event_id"].notna().all()


def test_valid_mask_shape_and_dtype(sample_chip) -> None:
    valid = valid_mask(sample_chip)
    assert valid.shape == (512, 512)
    assert valid.dtype == bool


def test_channel_stack_shapes_for_all_configs(sample_chip) -> None:
    for names in BS_CONFIGS.values():
        stack = bs_channel_stack(sample_chip, names)
        assert stack.shape == (512, 512, len(names))
        assert np.isfinite(stack).all()


def test_mask_values_in_range(sample_chip) -> None:
    assert set(np.unique(sample_chip.mask).tolist()) <= {0, 1, 2, 3}


def test_combined_loss_finite_and_improves_toward_target() -> None:
    import torch

    targets = torch.zeros(1, 8, 8, dtype=torch.long)
    targets[0, 2:4, 2:4] = 2
    targets[0, 0, 0] = 255
    criterion = CombinedLoss(class_weights=None, num_classes=4)
    bad_logits = torch.zeros(1, 4, 8, 8)
    good_logits = torch.zeros(1, 4, 8, 8)
    good_logits[0, 0] = 5.0
    good_logits[0, 2, 2:4, 2:4] = 10.0
    good_logits[0, 0, 2:4, 2:4] = -10.0
    bad = criterion(bad_logits, targets).item()
    good = criterion(good_logits, targets).item()
    assert np.isfinite(bad) and np.isfinite(good)
    assert good < bad


def test_hierarchical_loss_handles_ignore_index_and_improves_toward_target() -> None:
    import torch

    targets = torch.zeros(1, 8, 8, dtype=torch.long)
    targets[0, 2:4, 2:4] = 2
    targets[0, 0, 0] = 255
    criterion = BurnSeverityLoss(class_weights=None)
    bad_logits = torch.zeros(1, 4, 8, 8)
    good_logits = torch.zeros(1, 4, 8, 8)
    good_logits[0, 0] = 5.0
    good_logits[0, 2, 2:4, 2:4] = 10.0
    good_logits[0, 0, 2:4, 2:4] = -10.0
    bad = criterion(bad_logits, targets).item()
    good = criterion(good_logits, targets).item()
    assert np.isfinite(bad) and np.isfinite(good)
    assert good < bad


def test_hierarchical_loss_all_ignored_is_finite() -> None:
    import torch

    targets = torch.full((1, 4, 4), 255, dtype=torch.long)
    criterion = BurnSeverityLoss(class_weights=None)
    logits = torch.zeros(1, 4, 4, 4)
    loss = criterion(logits, targets)
    assert np.isfinite(loss.item())


def test_evaluate_predictions_perfect_match_gives_iou_one() -> None:
    pred = np.zeros((4, 4), dtype=np.int64)
    pred[0:2, 0:2] = 1
    true = pred.copy()
    valid = np.ones_like(pred, dtype=bool)
    metrics = evaluate_predictions([pred], [true], [valid])
    assert metrics["iou_burn"] == pytest.approx(1.0)
    assert metrics["miou_severity"] == pytest.approx(1.0)


def test_rle_roundtrip_empty_and_nonempty() -> None:
    empty = np.zeros((10, 10), dtype=np.uint8)
    assert decode_rle(encode_rle(empty), (10, 10)).sum() == 0
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[3:5, 2:7] = 1
    assert np.array_equal(decode_rle(roundtrip_check(mask), (10, 10)), mask)


def test_multiclass_to_binary_rles_no_overlap() -> None:
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[0:2, 0:2] = 1
    mask[3:5, 3:5] = 2
    rles = multiclass_to_binary_rles(mask, (1, 2, 3))
    decoded = {c: decode_rle(v, (6, 6)) for c, v in rles.items()}
    total = decoded[1] + decoded[2] + decoded[3]
    assert (total <= 1).all()
