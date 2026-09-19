from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest
import tifffile
from app.services.upload_inference import _read_archive, predict_upload
from fastapi import HTTPException


def chip_archive(task: str, *, omit: str = "", mixed: bool = False) -> bytes:
    assets = (
        [("VIIRS_I1-I5", 8), ("AUX", 5)]
        if task == "af"
        else [
            ("Sentinel-2_pre", 10),
            ("Sentinel-2_post", 10),
            ("Sentinel-1_pre", 2),
            ("Sentinel-1_post", 2),
            ("AUX", 3),
        ]
    )
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for suffix, bands in assets:
            if suffix == omit:
                continue
            array = np.ones((256, 256, bands), dtype=np.float32)
            if bands == 10:
                array[..., 9] = 4
            raster = io.BytesIO()
            tifffile.imwrite(raster, array, photometric="minisblack")
            cid = "other" if mixed and suffix == "AUX" else "ownchip"
            archive.writestr(f"nested/{cid}_{suffix}.tif", raster.getvalue())
    return result.getvalue()


@pytest.mark.parametrize("task,count", [("af", 2), ("bs", 5)])
def test_upload_accepts_complete_chip(task: str, count: int) -> None:
    chip_id, assets, preview = _read_archive(task, chip_archive(task))
    assert chip_id == "ownchip"
    assert len(assets) == count
    assert preview.shape[:2] == (256, 256)


@pytest.mark.parametrize(
    "data,detail",
    [
        (chip_archive("af", omit="AUX"), "AUX"),
        (chip_archive("af", mixed=True), "один и тот же ID"),
        (b"not a zip", "ZIP"),
    ],
)
def test_upload_rejects_incomplete_or_invalid_chip(data: bytes, detail: str) -> None:
    with pytest.raises(HTTPException) as error:
        _read_archive("af", data)
    assert error.value.status_code == 422
    assert detail in error.value.detail


def test_upload_runs_model_from_temporary_chip(monkeypatch: pytest.MonkeyPatch) -> None:
    from kroma_ml import service

    def fake_predict(chip_id: str, root: str) -> dict:
        from pathlib import Path

        assert chip_id == "ownchip"
        assert (Path(root) / "viirs" / "ownchip_VIIRS_I1-I5.tif").is_file()
        assert (Path(root) / "aux" / "ownchip_AUX.tif").is_file()
        assert not (Path(root) / "masks").exists()
        return {
            "mask": np.zeros((256, 256), np.uint8),
            "probability": np.zeros((256, 256), np.float32),
            "fire_pixels": 0,
            "model_version": "test-af",
        }

    monkeypatch.setattr(service, "predict_af", fake_predict)
    result = predict_upload("af", "my.zip", chip_archive("af"))
    assert result["status"] == "ok"
    assert result["model_version"] == "test-af"
    assert result["input"]["chip_id"] == "ownchip"
    assert result["mask_png_b64"]
    assert result["metrics"] == {}
