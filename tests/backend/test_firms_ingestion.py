import json
from pathlib import Path

import pytest
from app.schemas.observations import HotspotObservation
from app.services.firms import normalize_csv

HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
)
ROW = "55.12345,37.12345,330.44,0.40,0.37,2023-07-12,631,N,VIIRS,n,2.0NRT,295.66,2.24,D\n"


def test_normalization_deduplicates_and_preserves_utc(tmp_path: Path) -> None:
    input_path = tmp_path / "firms.csv"
    output_path = tmp_path / "observations.jsonl"
    input_path.write_text(HEADER + ROW + ROW)

    assert normalize_csv(input_path, output_path, "VIIRS_SNPP_NRT") == 1
    observation = HotspotObservation.model_validate(json.loads(output_path.read_text()))

    assert observation.acquired_at.isoformat() == "2023-07-12T06:31:00+00:00"
    assert observation.source_confidence == "n"
    assert observation.frp_mw == 2.24
    first_output = output_path.read_bytes()
    assert normalize_csv(input_path, output_path, "VIIRS_SNPP_NRT") == 1
    assert output_path.read_bytes() == first_output


def test_invalid_input_does_not_replace_previous_output(tmp_path: Path) -> None:
    input_path = tmp_path / "firms.csv"
    output_path = tmp_path / "observations.jsonl"
    input_path.write_text(HEADER + ROW)
    normalize_csv(input_path, output_path, "VIIRS_SNPP_NRT")
    first_output = output_path.read_bytes()
    input_path.write_text(HEADER + ROW.replace("55.12345", "955.12345"))

    with pytest.raises(ValueError, match="invalid FIRMS row 2"):
        normalize_csv(input_path, output_path, "VIIRS_SNPP_NRT")

    assert output_path.read_bytes() == first_output


def test_input_cannot_be_overwritten(tmp_path: Path) -> None:
    input_path = tmp_path / "firms.csv"
    input_path.write_text(HEADER + ROW)

    with pytest.raises(ValueError, match="input and output paths must differ"):
        normalize_csv(input_path, input_path, "VIIRS_SNPP_NRT")

    assert input_path.read_text() == HEADER + ROW
