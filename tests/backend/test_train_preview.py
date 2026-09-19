from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import tifffile
from app.services.train_dataset import ASSET_PATHS, TrainDatasetService


def test_inspector_previews_from_mounted_train(tmp_path: Path) -> None:
    chip_id = "BS_tr_000001"
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"chips": [{"chip_id": chip_id, "kind": "bs"}]}))
    train = tmp_path / "train"
    service = TrainDatasetService(index, tmp_path / "missing.tar", train)
    assert service.get_chip(chip_id)["inspector"]["assets_available"] is False

    bands = {"s2_pre": 10, "s2_post": 10, "s1_pre": 2, "s1_post": 2, "aux": 3}
    for asset, template in ASSET_PATHS["bs"].items():
        path = train / Path(template.format(id=chip_id)).relative_to("train")
        path.parent.mkdir(parents=True, exist_ok=True)
        if asset == "mask":
            array = np.zeros((256, 256), dtype=np.uint8)
        else:
            array = np.ones((256, 256, bands[asset]), dtype=np.float32)
        tifffile.imwrite(path, array, photometric="minisblack")

    assert service.get_chip(chip_id)["inspector"]["assets_available"] is True
    assert service.preview_png(chip_id, "s2_pre", 320).startswith(b"\x89PNG")
    assert service.preview_png(chip_id, "s2_post", 320).startswith(b"\x89PNG")
