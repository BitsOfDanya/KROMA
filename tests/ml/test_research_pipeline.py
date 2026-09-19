import json
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from kroma_ml.features import incident_features
from kroma_ml.incidents import Observation, cluster_incidents
from kroma_ml.priority import PriorityInputs, ThreatInputs, priority_score, threat_score
from kroma_ml.thermal_memory import EqualAreaGrid, ThermalMemory


def observation(
    identity: str, longitude: float, latitude: float, hours: int = 0, region: str = "RU-X"
) -> Observation:
    return Observation(
        identity,
        longitude,
        latitude,
        datetime(2023, 7, 12, tzinfo=UTC) + timedelta(hours=hours),
        "VIIRS_SNPP_NRT",
        "N",
        5.0,
        "n",
        "N",
        330.0,
        0.5,
        0.5,
        region,
    )


def test_clustering_uses_haversine_time_and_antimeridian() -> None:
    observations = [
        observation("a", 179.99, 60),
        observation("b", -179.99, 60, 1),
        observation("c", 179.99, 60, 48),
    ]
    result = cluster_incidents(observations, eps_km=2, time_window_hours=3, min_samples=2)
    assert len(result.incidents) == 1
    assert result.incidents[0].observation_ids == ("a", "b")
    assert result.noise_ids == ("c",)


def test_thermal_memory_excludes_future_and_explains_history() -> None:
    history = [
        observation("past", 70, 60, -24),
        observation("future", 70, 60, 24),
    ]
    memory = ThermalMemory(history, EqualAreaGrid(2))
    profile = memory.profile(
        70, 60, datetime(2023, 7, 12, tzinfo=UTC), datetime(2020, 7, 12, tzinfo=UTC), "RU-X"
    )
    assert profile.historical_detection_count == 1
    assert profile.active_days == 1
    assert profile.last_seen_before_event == history[0].acquired_at
    assert "1 detections" in profile.reason


def test_priority_components_and_validation() -> None:
    threat = threat_score(ThreatInputs(1, 0.5, 0.5, 0, 0))
    assert threat["score"] == 0.475
    result = priority_score(PriorityInputs(0.8, threat["score"], 0.5, 0.2, 1))
    assert result["score"] == pytest.approx(
        sum(value for name, value in result.items() if name != "score")
    )
    with pytest.raises(ValueError):
        priority_score(PriorityInputs(float("nan"), 0, 0, 0, 0))


def test_feature_matrix_separates_native_sensor_confidence() -> None:
    viirs = observation("v", 70, 60)
    modis = Observation(
        "m",
        70.01,
        60,
        viirs.acquired_at,
        "MODIS_TERRA_SP",
        "T",
        10.0,
        80,
        "D",
        320.0,
        1.0,
        1.0,
        "RU-X",
    )
    incident = cluster_incidents([viirs, modis], eps_km=2).incidents[0]
    features = incident_features(incident, [viirs, modis])
    assert features["modis_native_confidence_mean"] == 80
    assert features["viirs_high_ratio"] == 0
    assert features["thermal_novelty_score"] is None


def test_pilot_rejects_input_checksum_mismatch(tmp_path) -> None:
    run = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/prepare/pilot.py"))[
        "run"
    ]
    input_path = tmp_path / "observations.jsonl"
    input_path.write_text("")
    config = tmp_path / "pilots.json"
    config.write_text(json.dumps({"input_sha256": "wrong", "pilots": []}))
    with pytest.raises(ValueError, match="SHA-256"):
        run(input_path, config, tmp_path / "out", tmp_path / "manifest.json")


def test_pilot_context_respects_extract_coverage(tmp_path) -> None:
    functions = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/prepare/pilot.py")
    )
    feature = {
        "type": "Feature",
        "properties": {"category": "road", "name": "Road"},
        "geometry": {"type": "Point", "coordinates": [86.1, 54.3]},
    }
    path = tmp_path / "context.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
    import hashlib

    settings = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bbox": [86.0, 54.2, 86.2, 54.4],
    }
    features, checksum = functions["_context_source"](settings)
    assert checksum == settings["sha256"]
    inside, inputs = functions["_incident_context"](86.1, 54.3, settings, features)
    assert inside["status"] == "partial_coverage"
    assert inputs["distance_to_road_km"] == 0
    assert inputs["protected_area_intersection"] is None
    outside, inputs = functions["_incident_context"](87, 54.3, settings, features)
    assert outside == {"status": "outside_coverage"}
    assert inputs == {}
    settings["sha256"] = "wrong"
    with pytest.raises(ValueError, match="context SHA-256"):
        functions["_context_source"](settings)
