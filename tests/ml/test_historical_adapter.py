import hashlib
import runpy
from argparse import Namespace
from datetime import date
from pathlib import Path

adapter = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/ingestion/historical_firms.py")
)
_normalized_rows = adapter["_normalized_rows"]
_cache_path = adapter["_cache_path"]
run = adapter["run"]


def test_modis_adapter_preserves_sensor_specific_brightness(tmp_path) -> None:
    raw = tmp_path / "modis.csv"
    raw.write_text(
        "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight\n"
        "60,90,320,1,1,2023-07-12,123,T,70,6.1,300,12,N\n"
        "60.1,90.1,321,1,1,2023-07-12,124,A,80,6.1,301,13,D\n"
    )
    rows = list(_normalized_rows(raw, "MODIS_SP"))
    assert {row["source"] for row in rows} == {"MODIS_TERRA_SP", "MODIS_AQUA_SP"}
    assert rows[0]["brightness_ti4_kelvin"] is None
    assert rows[0]["brightness_modis_kelvin"] == 320
    assert rows[0]["source_confidence"] == 70


def test_viirs_sp_adapter_reuses_existing_normalizer(tmp_path) -> None:
    raw = tmp_path / "viirs.csv"
    raw.write_text(
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
        "60,90,330,0.4,0.4,2023-07-12,123,N,n,2.0,300,12,N\n"
    )
    nrt = next(_normalized_rows(raw, "VIIRS_SNPP_NRT"))
    standard = next(_normalized_rows(raw, "VIIRS_SNPP_SP"))
    assert nrt["source"] == "VIIRS_SNPP_NRT"
    assert standard["source"] == "VIIRS_SNPP_SP"
    assert nrt["observation_id"] != standard["observation_id"]
    assert standard["brightness_ti4_kelvin"] == 330


def test_historical_cache_and_manifest_work_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NASA_FIRMS_API_KEY", raising=False)
    bbox = (89.0, 59.0, 91.0, 61.0)
    content = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
        "60,90,330,0.4,0.4,2023-07-12,123,N,n,2.0,300,12,N\n"
    )
    for west in (89.0, 90.0):
        for south in (59.0, 60.0):
            tile = (west, south, west + 1, south + 1)
            raw = _cache_path("VIIRS_SNPP_SP", tile, date(2023, 7, 12), 1)
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(content)
    args = Namespace(
        date_from=date(2023, 7, 12),
        date_to=date(2023, 7, 12),
        region_code=None,
        regions=None,
        aoi=None,
        bbox=bbox,
        tile_degrees=1,
        sources=["VIIRS_SNPP_SP"],
        output=Path("data/interim/test.jsonl"),
        manifest=Path("research/experiments/test.manifest.json"),
    )
    manifest = run(args)
    assert manifest["number_of_observations"] == 1
    assert len(manifest["chunks"]) == 4
    assert all(chunk["cached"] for chunk in manifest["chunks"])
    assert args.output.exists()
    assert manifest["output_sha256"] == hashlib.sha256(args.output.read_bytes()).hexdigest()
