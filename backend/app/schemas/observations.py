from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class HotspotObservation(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    observation_id: str = Field(min_length=1)
    source: Literal["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
    satellite: Literal["N", "N20", "N21"]
    acquired_at: AwareDatetime
    location: Coordinates
    brightness_ti4_kelvin: float = Field(allow_inf_nan=False)
    brightness_ti5_kelvin: float | None = Field(default=None, allow_inf_nan=False)
    frp_mw: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    scan_km: float = Field(gt=0, allow_inf_nan=False)
    track_km: float = Field(gt=0, allow_inf_nan=False)
    source_confidence: Literal["l", "n", "h"]
    daynight: Literal["D", "N"]
    source_version: str = Field(min_length=1)


class FireEvent(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(min_length=1)
    first_observed_at: AwareDatetime
    last_observed_at: AwareDatetime
    centroid: Coordinates
    observation_ids: list[str] = Field(min_length=1)
    kroma_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    priority_score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.first_observed_at > self.last_observed_at:
            raise ValueError("first_observed_at must not exceed last_observed_at")
        return self
