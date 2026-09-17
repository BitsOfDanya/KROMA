from kroma_geo.measure import point_in_bbox

from app.core.config import get_settings
from app.live.models import LiveStatus
from app.live.store import LiveStore
from app.models.geometry import BBox
from app.schemas.geojson import CollectionMeta, Feature, FeatureCollection


class LiveService:
    def __init__(self, store: LiveStore) -> None:
        self.store = store

    def status(self) -> LiveStatus:
        return self.store.status()

    def hotspots(self, bbox: BBox | None) -> FeatureCollection:
        features = [
            Feature(
                id=item.id,
                geometry={"type": "Point", "coordinates": list(item.location)},
                properties={
                    "t": int(item.acquired_at.timestamp()),
                    "incident_id": None,
                    "classification": "unassigned",
                    "satellite": item.satellite,
                    "instrument": item.instrument,
                    "frp_mw": item.frp_mw or 0.0,
                    "brightness_k": item.brightness_k,
                    "confidence": item.source_confidence,
                    "daynight": item.daynight,
                    "pixel_size_m": item.pixel_size_m,
                },
            )
            for item in self.store.detections()
            if bbox is None or point_in_bbox(item.location, bbox)
        ]
        return FeatureCollection(features=features, meta=CollectionMeta(count=len(features)))

    def incidents(self, bbox: BBox | None) -> FeatureCollection:
        features = [
            Feature(
                id=item.id,
                geometry={"type": "Point", "coordinates": list(item.centroid)},
                properties={
                    "id": item.id,
                    "status": item.status,
                    "severity": item.severity,
                    "priority": item.priority,
                    "confidence": item.priority,
                    "threat": item.priority,
                    "area_ha": None,
                    "district": "",
                    "region": "",
                    "detection_count": item.detection_count,
                    "frp_mw": item.frp_mw,
                    "sources": ", ".join(item.sources),
                    "first_detected": int(item.first_detected_at.timestamp()),
                    "updated": int(item.updated_at.timestamp()),
                },
            )
            for item in self.store.incidents()
            if bbox is None or point_in_bbox(item.centroid, bbox)
        ]
        return FeatureCollection(features=features, meta=CollectionMeta(count=len(features)))


def build_store() -> LiveStore:
    return LiveStore(get_settings())


_store: LiveStore | None = None


def get_live_store() -> LiveStore:
    global _store
    if _store is None:
        _store = build_store()
    return _store


def get_live_service() -> LiveService:
    return LiveService(get_live_store())
