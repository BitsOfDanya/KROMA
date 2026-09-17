from typing import Any, Literal

from pydantic import BaseModel, Field


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: str | int | None = None
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class CollectionMeta(BaseModel):
    count: int
    crs: Literal["EPSG:4326"] = "EPSG:4326"
    aggregated: bool = False


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]
    meta: CollectionMeta
