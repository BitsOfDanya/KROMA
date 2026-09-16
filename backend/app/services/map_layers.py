import math
from collections import defaultdict
from datetime import datetime

from app.models.context import RiskObjectKind
from app.models.geometry import BBox
from app.models.observation import Observation, ObservationClass
from app.repositories.base import FireDataRepository, ObservationQuery
from app.schemas.geojson import CollectionMeta, Feature, FeatureCollection
from app.services.incidents import IncidentService

OPEN_ENDED_EPOCH = 4_102_444_800
AGGREGATION_ZOOM = 3.0


def _epoch(value: datetime | None) -> int:
    return OPEN_ENDED_EPOCH if value is None else int(value.timestamp())


def _collection(features: list[Feature], aggregated: bool = False) -> FeatureCollection:
    return FeatureCollection(
        features=features, meta=CollectionMeta(count=len(features), aggregated=aggregated)
    )


def observation_feature(item: Observation) -> Feature:
    return Feature(
        id=item.id,
        geometry={"type": "Point", "coordinates": list(item.location)},
        properties={
            "t": _epoch(item.acquired_at),
            "incident_id": item.incident_id,
            "classification": item.classification,
            "satellite": item.satellite,
            "instrument": item.instrument,
            "frp_mw": item.frp_mw,
            "brightness_k": item.brightness_k,
            "confidence": item.source_confidence,
            "daynight": item.daynight,
            "pixel_size_m": item.pixel_size_m,
        },
    )


def _grid_cell_size(zoom: float) -> float:
    return 4.0 if zoom < 2 else 2.0


class MapLayerService:
    def __init__(self, repository: FireDataRepository) -> None:
        self.repository = repository
        self.incidents = IncidentService(repository)

    def incidents_layer(self, bbox: BBox | None) -> FeatureCollection:
        features = []
        for item in self.incidents.all_summaries():
            if bbox and not (
                bbox[0] <= item.centroid[0] <= bbox[2] and bbox[1] <= item.centroid[1] <= bbox[3]
            ):
                continue
            features.append(
                Feature(
                    id=item.id,
                    geometry={"type": "Point", "coordinates": list(item.centroid)},
                    properties={
                        "id": item.id,
                        "status": item.status,
                        "severity": item.severity,
                        "priority": item.priority,
                        "confidence": item.confidence,
                        "threat": item.threat,
                        "area_ha": item.area_ha,
                        "district": item.district,
                        "region": item.region,
                        "first_detected": _epoch(item.first_detected_at),
                        "updated": _epoch(item.updated_at),
                    },
                )
            )
        return _collection(features)

    def hotspots_layer(
        self,
        bbox: BBox | None,
        zoom: float | None,
        start: datetime | None,
        end: datetime | None,
        classifications: tuple[ObservationClass, ...] | None,
    ) -> FeatureCollection:
        observations = self.repository.observations(
            ObservationQuery(bbox=bbox, start=start, end=end, classifications=classifications)
        )
        if zoom is not None and zoom < AGGREGATION_ZOOM:
            return self._aggregate(observations, _grid_cell_size(zoom))
        return _collection([observation_feature(item) for item in observations])

    def _aggregate(self, observations: list[Observation], cell: float) -> FeatureCollection:
        buckets: dict[tuple[int, int], list[Observation]] = defaultdict(list)
        for item in observations:
            key = (math.floor(item.location[0] / cell), math.floor(item.location[1] / cell))
            buckets[key].append(item)
        features = []
        for (x, y), items in sorted(buckets.items()):
            lon = sum(item.location[0] for item in items) / len(items)
            lat = sum(item.location[1] for item in items) / len(items)
            latest = max(item.acquired_at for item in items)
            features.append(
                Feature(
                    id=f"cell-{x}-{y}",
                    geometry={"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]},
                    properties={
                        "count": len(items),
                        "t": _epoch(latest),
                        "frp_mw": round(sum(item.frp_mw for item in items), 1),
                        "classification": "aggregate",
                    },
                )
            )
        return _collection(features, aggregated=True)

    def perimeters_layer(self, bbox: BBox | None, incident_id: str | None) -> FeatureCollection:
        severities = {item.id: item for item in self.incidents.all_summaries()}
        features = []
        for state in self.repository.perimeters(incident_id):
            summary = severities.get(state.incident_id)
            if summary is None:
                continue
            if bbox and not (
                summary.bbox[0] <= bbox[2]
                and summary.bbox[2] >= bbox[0]
                and summary.bbox[1] <= bbox[3]
                and summary.bbox[3] >= bbox[1]
            ):
                continue
            properties = {
                "incident_id": state.incident_id,
                "severity": summary.severity,
                "status": summary.status,
                "valid_from": _epoch(state.observed_at),
                "valid_to": _epoch(state.valid_until),
                "area_ha": state.area_ha,
            }
            features.append(
                Feature(
                    id=f"{state.incident_id}-perimeter-{_epoch(state.observed_at)}",
                    geometry=state.perimeter.model_dump(),
                    properties={**properties, "kind": "perimeter"},
                )
            )
            if len(state.active_front.coordinates) > 1:
                features.append(
                    Feature(
                        id=f"{state.incident_id}-front-{_epoch(state.observed_at)}",
                        geometry=state.active_front.model_dump(),
                        properties={**properties, "kind": "front"},
                    )
                )
        return _collection(features)

    def forecast_layer(self, incident_id: str) -> FeatureCollection:
        incident = self.incidents.get(incident_id)
        features = [
            Feature(
                id=zone.id,
                geometry=zone.geometry.model_dump(),
                properties={
                    "incident_id": incident.id,
                    "level": zone.level,
                    "area_ha": zone.area_ha,
                    "horizon_hours": zone.horizon_hours,
                    "issued_at": zone.issued_at.isoformat(),
                    "valid_from": _epoch(zone.issued_at),
                },
            )
            for zone in sorted(
                self.repository.forecasts(incident.id), key=lambda zone: zone.level, reverse=True
            )
        ]
        return _collection(features)

    def incident_observations(self, incident_id: str) -> FeatureCollection:
        incident = self.incidents.get(incident_id)
        observations = self.repository.observations(ObservationQuery(incident_id=incident.id))
        return _collection([observation_feature(item) for item in observations])

    def burn_scars_layer(self, bbox: BBox | None) -> FeatureCollection:
        features = []
        for scar in self.repository.burn_scars():
            if bbox and not (
                scar.bbox[0] <= bbox[2]
                and scar.bbox[2] >= bbox[0]
                and scar.bbox[1] <= bbox[3]
                and scar.bbox[3] >= bbox[1]
            ):
                continue
            features.append(
                Feature(
                    id=scar.id,
                    geometry=scar.geometry.model_dump(),
                    properties={
                        "id": scar.id,
                        "kind": "scar",
                        "name": scar.name,
                        "area_ha": scar.area_ha,
                        "assessment": scar.assessment,
                        "incident_id": scar.incident_id,
                    },
                )
            )
            for zone in scar.zones:
                features.append(
                    Feature(
                        id=f"{scar.id}-{zone.severity}",
                        geometry=zone.geometry.model_dump(),
                        properties={
                            "id": scar.id,
                            "kind": "zone",
                            "severity": zone.severity,
                            "area_ha": zone.area_ha,
                        },
                    )
                )
        return _collection(features)

    def risk_objects_layer(
        self, bbox: BBox | None, kinds: tuple[RiskObjectKind, ...] | None
    ) -> FeatureCollection:
        features = [
            Feature(
                id=item.id,
                geometry=item.geometry.model_dump(),
                properties={
                    "id": item.id,
                    "kind": item.kind,
                    "name": item.name,
                    "subtitle": item.subtitle,
                    "population": item.population,
                },
            )
            for item in self.repository.risk_objects(bbox, kinds)
        ]
        return _collection(features)

    def thermal_sources_layer(self, bbox: BBox | None) -> FeatureCollection:
        features = [
            Feature(
                id=item.id,
                geometry={"type": "Point", "coordinates": list(item.location)},
                properties={
                    "id": item.id,
                    "name": item.name,
                    "kind": item.kind,
                    "observation_count": item.observation_count,
                    "history_years": item.history_years,
                    "mean_frp_mw": item.mean_frp_mw,
                    "last_seen_at": item.last_seen_at.isoformat(),
                },
            )
            for item in self.repository.thermal_sources(bbox)
        ]
        return _collection(features)

    def wind_layer(self, bbox: BBox | None) -> FeatureCollection:
        features = [
            Feature(
                id=f"wind-{index}",
                geometry={"type": "Point", "coordinates": list(item.location)},
                properties={
                    "from_deg": item.from_deg,
                    "to_deg": (item.from_deg + 180) % 360,
                    "speed_ms": item.speed_ms,
                },
            )
            for index, item in enumerate(self.repository.wind(bbox))
        ]
        return _collection(features)

    def clouds_layer(self, bbox: BBox | None) -> FeatureCollection:
        features = [
            Feature(
                id=item.id,
                geometry=item.geometry.model_dump(),
                properties={"id": item.id, "probability": item.probability},
            )
            for item in self.repository.clouds(bbox)
        ]
        return _collection(features)
