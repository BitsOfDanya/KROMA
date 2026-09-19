import csv
import io
import json
from pathlib import Path

import pytest
from app.repositories.prepared import PreparedDatasetRepository

BASE = (
    "dataset_id=kroma-ci-demo&dataset_version=1.0.0"
    "&bbox=99.03,58.03,99.13,58.13&from=2024-08-10&to=2024-08-20"
)


def test_analysis_catalog_readiness_and_openapi(api) -> None:
    catalog = api("/api/v1/analysis/datasets")
    readiness = api("/api/v1/analysis/readiness")
    schema = api("/openapi.json").json()

    assert catalog.status_code == 200
    item = catalog.json()["items"][0]
    assert item["origin"] == "synthetic_demo"
    assert item["example"]["bbox"] == [99.03, 58.03, 99.13, 58.13]
    assert readiness.json()["status"] == "ready"
    assert {
        "/api/v1/analysis",
        "/api/v1/analysis/datasets",
        "/api/v1/analysis/export/contours",
        "/api/v1/analysis/export/report",
    }.issubset(schema["paths"])


def test_analysis_is_consistent_and_deterministic(api) -> None:
    first = api(f"/api/v1/analysis?{BASE}").json()
    second = api(f"/api/v1/analysis?{BASE}").json()

    assert first["result_id"] == second["result_id"]
    assert first["generated_at"] != ""
    assert first["summary"]["hotspot_count"] == 2
    assert first["summary"]["zone_count"] == 3
    assert first["summary"]["burn_scar_count"] == 1
    areas = [item["area_ha"] for item in first["summary"]["severity"]]
    assert sum(areas) == pytest.approx(first["summary"]["total_burned_area_ha"], abs=1e-6)
    assert sum(
        feature["properties"]["area_ha"] for feature in first["burn_zones"]["features"]
    ) == pytest.approx(first["summary"]["total_burned_area_ha"], abs=1e-6)
    assert all(
        feature["properties"]["result_id"] == first["result_id"]
        for feature in first["burn_zones"]["features"]
    )


def test_inclusive_dates_and_latest_assessment_rule(api) -> None:
    one_day = api(
        "/api/v1/analysis?dataset_id=kroma-ci-demo&dataset_version=1.0.0"
        "&bbox=99.0,58.0,99.2,58.2&from=2024-08-20&to=2024-08-20"
    ).json()
    old = api(
        "/api/v1/analysis?dataset_id=kroma-ci-demo&dataset_version=1.0.0"
        "&bbox=99.0,58.0,99.2,58.2&from=2024-08-10&to=2024-08-12"
    ).json()
    latest = api(f"/api/v1/analysis?{BASE}").json()

    assert [item["id"] for item in one_day["hotspots"]["features"]] == ["AF-DEMO-003"]
    assert {item["properties"]["assessment_id"] for item in old["burn_zones"]["features"]} == {
        "ASSESS-A-20240812"
    }
    assert {item["properties"]["assessment_id"] for item in latest["burn_zones"]["features"]} == {
        "ASSESS-A-20240815"
    }


def test_clipping_changes_area_and_keeps_geometry_in_bbox(api) -> None:
    full = api(f"/api/v1/analysis?{BASE}").json()
    clipped_query = BASE.replace("99.03,58.03,99.13,58.13", "99.03,58.03,99.06,58.13")
    clipped = api(f"/api/v1/analysis?{clipped_query}").json()

    assert clipped["result_id"] != full["result_id"]
    assert clipped["summary"]["total_burned_area_ha"] < full["summary"]["total_burned_area_ha"]
    for feature in clipped["burn_zones"]["features"]:
        text = json.dumps(feature["geometry"])
        assert "NaN" not in text
        coordinates = feature["geometry"]["coordinates"]
        flattened = []

        def visit(value):
            if (
                isinstance(value, list)
                and len(value) == 2
                and all(isinstance(item, int | float) for item in value)
            ):
                flattened.append(value)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(coordinates)
        assert all(99.03 <= lon <= 99.06 and 58.03 <= lat <= 58.13 for lon, lat in flattened)


def test_empty_and_no_coverage_are_different(api) -> None:
    empty = api(
        "/api/v1/analysis?dataset_id=kroma-ci-demo&dataset_version=1.0.0"
        "&bbox=99.03,58.03,99.13,58.13&from=2024-08-25&to=2024-08-26"
    ).json()
    missing = api(
        "/api/v1/analysis?dataset_id=kroma-ci-demo&dataset_version=1.0.0"
        "&bbox=100,59,100.1,59.1&from=2024-08-10&to=2024-08-20"
    ).json()

    assert empty["summary"]["status"] == "empty"
    assert empty["summary"]["total_burned_area_ha"] == 0
    assert missing["summary"]["status"] == "no_coverage"
    assert missing["summary"]["total_burned_area_ha"] is None
    assert all(item["area_ha"] is None for item in missing["summary"]["severity"])


def test_validation_errors(api) -> None:
    prefix = "/api/v1/analysis?dataset_id=kroma-ci-demo&dataset_version=1.0.0"
    assert api(f"{prefix}&bbox=99,58,99,59&from=2024-08-10&to=2024-08-20").status_code == 422
    assert api(f"{prefix}&bbox=NaN,58,99,59&from=2024-08-10&to=2024-08-20").status_code == 422
    assert api(f"{prefix}&bbox=99,58,100,59&from=2024-08-20&to=2024-08-10").status_code == 422
    assert api(f"{prefix}&bbox=99,58,100,59&from=2020-01-01&to=2024-08-10").status_code == 422
    assert (
        api(
            f"{prefix.replace('1.0.0', '9.9.9')}&bbox=99,58,100,59&from=2024-08-10&to=2024-08-20"
        ).status_code
        == 404
    )


def test_exports_round_trip_and_conflict(api) -> None:
    result = api(f"/api/v1/analysis?{BASE}").json()
    result_id = result["result_id"]
    contours = api(f"/api/v1/analysis/export/contours?{BASE}&expected_result_id={result_id}")
    report = api(f"/api/v1/analysis/export/report?{BASE}&expected_result_id={result_id}&format=csv")
    json_report = api(
        f"/api/v1/analysis/export/report?{BASE}&expected_result_id={result_id}&format=json"
    )
    conflict = api(f"/api/v1/analysis/export/contours?{BASE}&expected_result_id=ar_stale")

    assert contours.status_code == 200
    assert contours.headers["content-type"].startswith("application/geo+json")
    assert "attachment; filename=" in contours.headers["content-disposition"]
    exported = contours.json()
    assert exported["result_id"] == result_id
    assert len(exported["features"]) == result["summary"]["zone_count"]

    rows = list(csv.DictReader(io.StringIO(report.content.decode("utf-8-sig"))))
    assert report.headers["content-type"].startswith("text/csv")
    assert [row["row_type"] for row in rows] == ["total", "severity", "severity", "severity"]
    assert {row["result_id"] for row in rows} == {result_id}
    assert json_report.json()["result_id"] == result_id
    assert conflict.status_code == 409


def test_checksum_mismatch_is_detected(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "backend" / "app" / "prepared_data"
    target = tmp_path / "dataset"
    target.mkdir()
    for path in source.iterdir():
        if path.is_file():
            (target / path.name).write_bytes(path.read_bytes())
    (target / "hotspots.geojson").write_text("{}", encoding="utf-8")

    repository = PreparedDatasetRepository(target)

    assert repository.list() == []
    assert any("Checksum mismatch" in error for error in repository.errors)
