import io
import zipfile

import numpy as np
import shapefile
from app.services.exports import shapefile_zip
from app.services.prediction import bs_metrics
from kroma_geo.raster_vector import ChipGeoreference, class_features
from kroma_ml import artifacts


def test_missing_mount_does_not_fall_back_to_research(tmp_path, monkeypatch):
    monkeypatch.setenv("KROMA_ML_ARTIFACTS_PATH", str(tmp_path))
    state = artifacts.status()
    assert not state["af"]["ready"]
    assert not state["bs"]["ready"]
    assert len(state["missing_artifacts"]) == 7


def test_shapefile_roundtrip_preserves_area_crs_and_provenance():
    mask = np.array([[1, 1], [2, 3]], dtype=np.uint8)
    features = class_features(
        mask,
        ChipGeoreference(32637, 600000, 5200000, 20, 20),
        classes={1: "low", 2: "moderate", 3: "high"},
        scene_id="BS_tr_demo",
        model_version="bs-v006",
        source="model_output",
    )
    assert sum(f["properties"]["area_ha"] for f in features) == 0.16
    assert all(f["properties"]["contour_id"] for f in features)
    with zipfile.ZipFile(io.BytesIO(shapefile_zip(features, "burn"))) as archive:
        assert {"burn.shp", "burn.shx", "burn.dbf", "burn.prj", "burn.cpg"} == set(
            archive.namelist()
        )
        assert b"WGS_1984" in archive.read("burn.prj")
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read("burn.shp")),
            shx=io.BytesIO(archive.read("burn.shx")),
            dbf=io.BytesIO(archive.read("burn.dbf")),
        )
        assert len(reader) == 3
        assert all(r.as_dict()["model_ver"] == "bs-v006" for r in reader.records())
        assert sum(r.as_dict()["area_ha"] for r in reader.records()) == 0.16


def test_bs_confusion_matrix_uses_only_valid_pixels():
    gt = np.array([[0, 1], [2, 255]], dtype=np.uint8)
    pred = np.array([[1, 1], [3, 0]], dtype=np.uint8)
    metrics = bs_metrics(pred, gt, gt != 255)
    assert metrics["confusion"] == [[0, 1, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 0, 0]]
