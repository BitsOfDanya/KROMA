from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.geometry import BBox
from app.schemas.geojson import FeatureCollection

Origin = Literal["model_output", "reference", "synthetic_demo"]
CoverageStatus = Literal["full", "partial", "none"]
SummaryStatus = Literal["ok", "empty", "no_coverage", "no_valid_data"]


class ArtifactManifest(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SceneManifest(BaseModel):
    scene_id: str
    satellite: str
    acquired_at: datetime
    role: Literal["before", "after", "observation"]
    cloud_cover_pct: float | None = Field(default=None, ge=0, le=100)


class ExampleQuery(BaseModel):
    bbox: BBox
    start: date = Field(alias="from", serialization_alias="from")
    end: date = Field(alias="to", serialization_alias="to")

    model_config = ConfigDict(populate_by_name=True)


class PreparedDatasetManifest(BaseModel):
    schema_version: str
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    dataset_version: str
    name: str
    description: str
    origin: Origin
    processing_version: str
    available_from: date
    available_to: date
    extent: BBox
    af_coverage: dict[str, Any] | None
    bs_coverage: dict[str, Any] | None
    bs_valid_coverage: dict[str, Any] | None
    area_crs: str
    source_crs: str
    mask: dict[str, Any]
    observation_source: str
    temporal_rule: str
    license: str
    attribution: str
    distribution: str
    example: ExampleQuery
    scenes: list[SceneManifest]
    artifacts: dict[str, ArtifactManifest]

    @model_validator(mode="after")
    def validate_dates(self) -> PreparedDatasetManifest:
        if self.available_from > self.available_to:
            raise ValueError("available_from must not exceed available_to")
        required = {"hotspots", "burn_zones"}
        if not required.issubset(self.artifacts):
            raise ValueError("manifest must contain hotspots and burn_zones artifacts")
        return self


class DatasetCatalogItem(BaseModel):
    dataset_id: str
    dataset_version: str
    name: str
    description: str
    origin: Origin
    processing_version: str
    available_from: date
    available_to: date
    extent: BBox
    example: ExampleQuery
    scene_ids: list[str]
    attribution: str
    license: str
    limitations: list[str]


class DatasetCatalogResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    items: list[DatasetCatalogItem]


class AnalysisRequest(BaseModel):
    dataset_id: str
    dataset_version: str
    bbox: BBox
    start: date = Field(alias="from", serialization_alias="from")
    end: date = Field(alias="to", serialization_alias="to")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: BBox) -> BBox:
        min_lon, min_lat, max_lon, max_lat = value
        if not all(number == number and abs(number) != float("inf") for number in value):
            raise ValueError("bbox coordinates must be finite")
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise ValueError("bbox must be a non-empty WGS84 extent without antimeridian crossing")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> AnalysisRequest:
        if self.start > self.end:
            raise ValueError("'from' must not exceed 'to'")
        return self


class Provenance(BaseModel):
    origin: Origin
    processing_version: str
    scene_ids: list[str]
    observation_source: str
    attribution: str
    license: str
    temporal_rule: str


class SourceCoverage(BaseModel):
    status: CoverageStatus
    covered_area_ha: float | None
    valid_area_ha: float | None = None


class Coverage(BaseModel):
    status: CoverageStatus
    query_area_ha: float
    covered_area_ha: float | None
    valid_area_ha: float | None
    active_fire: SourceCoverage
    burn_scars: SourceCoverage
    method: str


class SeveritySummary(BaseModel):
    class_id: Literal[1, 2, 3]
    label: str
    severity: Literal["low", "moderate", "high"]
    area_ha: float | None
    share: float | None


class AnalysisSummary(BaseModel):
    status: SummaryStatus
    hotspot_count: int
    burn_scar_count: int
    zone_count: int
    total_burned_area_ha: float | None
    severity: list[SeveritySummary]


class AnalysisWarning(BaseModel):
    code: str
    message: str


class CalculationMetadata(BaseModel):
    area_method: str
    area_crs: str
    clipping_rule: str
    deduplication_rule: str
    precision: str


class AnalysisResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    result_id: str
    request: AnalysisRequest
    provenance: Provenance
    coverage: Coverage
    summary: AnalysisSummary
    hotspots: FeatureCollection
    burn_zones: FeatureCollection
    warnings: list[AnalysisWarning]
    calculation: CalculationMetadata
    generated_at: datetime


class ApiErrorResponse(BaseModel):
    code: str
    message: str
