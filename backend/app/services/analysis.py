from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from time import perf_counter
from typing import Any

from kroma_geo.vector import (
    assert_non_overlapping,
    bbox_geometry,
    clip_to_bbox,
    geometry_area_ha,
)
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from app.core.config import Settings, get_settings
from app.models.geometry import BBox
from app.repositories.prepared import PreparedDataset, PreparedDatasetRepository
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisSummary,
    AnalysisWarning,
    CalculationMetadata,
    Coverage,
    DatasetCatalogItem,
    DatasetCatalogResponse,
    Provenance,
    SeveritySummary,
    SourceCoverage,
)
from app.schemas.geojson import CollectionMeta, Feature, FeatureCollection

SEVERITY = {
    1: ("low", "Слабая степень поражения"),
    2: ("moderate", "Средняя степень поражения"),
    3: ("high", "Сильная степень поражения"),
}

logger = logging.getLogger(__name__)


def _rounded(value: float) -> float:
    return round(value, 6)


def _coverage_status(covered: float, query: float) -> str:
    if covered <= 1e-9:
        return "none"
    if abs(covered - query) <= max(0.01, query * 1e-8):
        return "full"
    return "partial"


class AnalysisService:
    def __init__(
        self, repository: PreparedDatasetRepository, settings: Settings | None = None
    ) -> None:
        self.repository = repository
        self.settings = settings or get_settings()

    def catalog(self) -> DatasetCatalogResponse:
        items = []
        for dataset in self.repository.list():
            manifest = dataset.manifest
            limitations = [
                "Поддерживается только bbox без пересечения антимеридиана.",
                "Гари отбираются по дате послепожарной съёмки, а не по дате начала пожара.",
            ]
            if manifest.origin == "synthetic_demo":
                limitations.append(
                    "Синтетический проверочный набор: не является результатом модели "
                    "или реальными наблюдениями."
                )
            items.append(
                DatasetCatalogItem(
                    dataset_id=manifest.dataset_id,
                    dataset_version=manifest.dataset_version,
                    name=manifest.name,
                    description=manifest.description,
                    origin=manifest.origin,
                    processing_version=manifest.processing_version,
                    available_from=manifest.available_from,
                    available_to=manifest.available_to,
                    extent=manifest.extent,
                    example=manifest.example,
                    scene_ids=[scene.scene_id for scene in manifest.scenes],
                    attribution=manifest.attribution,
                    license=manifest.license,
                    limitations=limitations,
                )
            )
        return DatasetCatalogResponse(items=items)

    def readiness(self) -> dict[str, Any]:
        datasets = self.repository.list()
        return {
            "status": "ready" if datasets else "not_ready",
            "dataset_count": len(datasets),
            "datasets": [
                f"{item.manifest.dataset_id}@{item.manifest.dataset_version}" for item in datasets
            ],
            "errors": self.repository.errors,
        }

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = perf_counter()
        dataset = self.repository.get(request.dataset_id, request.dataset_version)
        query_area = geometry_area_ha(
            bbox_geometry(request.bbox), area_crs=dataset.manifest.area_crs
        )
        days = (request.end - request.start).days + 1
        if days > self.settings.analysis_max_days:
            raise ValueError(
                f"Date range exceeds configured limit of {self.settings.analysis_max_days} days"
            )
        if query_area > self.settings.analysis_max_area_ha:
            raise ValueError(
                f"Query area exceeds configured limit of {self.settings.analysis_max_area_ha:g} ha"
            )

        result_id = self._result_id(dataset, request)
        active_fire_coverage = self._source_coverage(
            dataset.manifest.af_coverage, request.bbox, query_area, dataset
        )
        burn_coverage = self._source_coverage(
            dataset.manifest.bs_coverage,
            request.bbox,
            query_area,
            dataset,
            dataset.manifest.bs_valid_coverage,
        )
        coverage = self._combined_coverage(
            dataset, request.bbox, query_area, active_fire_coverage, burn_coverage
        )

        hotspots = self._hotspots(dataset, request, result_id)
        zones, scene_ids = self._burn_zones(dataset, request, result_id)
        if len(hotspots) + len(zones) > self.settings.analysis_max_features:
            raise ValueError(
                f"Result exceeds configured limit of {self.settings.analysis_max_features} features"
            )

        warnings = self._warnings(dataset, active_fire_coverage, burn_coverage)
        summary = self._summary(hotspots, zones, active_fire_coverage, burn_coverage)
        relevant_scene_ids = sorted(scene_ids) or [
            scene.scene_id for scene in dataset.manifest.scenes
        ]

        result = AnalysisResult(
            result_id=result_id,
            request=request,
            provenance=Provenance(
                origin=dataset.manifest.origin,
                processing_version=dataset.manifest.processing_version,
                scene_ids=relevant_scene_ids,
                observation_source=dataset.manifest.observation_source,
                attribution=dataset.manifest.attribution,
                license=dataset.manifest.license,
                temporal_rule=dataset.manifest.temporal_rule,
            ),
            coverage=coverage,
            summary=summary,
            hotspots=FeatureCollection(
                features=hotspots,
                meta=CollectionMeta(count=len(hotspots), aggregated=False),
            ),
            burn_zones=FeatureCollection(
                features=zones,
                meta=CollectionMeta(count=len(zones), aggregated=False),
            ),
            warnings=warnings,
            calculation=CalculationMetadata(
                area_method="Площадь обрезанной геометрии в равноплощадной проекции / 10 000",
                area_crs=dataset.manifest.area_crs,
                clipping_rule="Пересечение Polygon/MultiPolygon с bbox в WGS84 до расчёта площади",
                deduplication_rule="Последняя полная assessment одного burn_event_id в периоде",
                precision="Расчёт double precision; API округляет гектары до 6 знаков",
            ),
            generated_at=datetime.now(UTC),
        )
        logger.info(
            "analysis_complete result_id=%s dataset=%s version=%s duration_ms=%.3f "
            "hotspots=%d zones=%d status=%s",
            result.result_id,
            request.dataset_id,
            request.dataset_version,
            (perf_counter() - started) * 1000,
            result.summary.hotspot_count,
            result.summary.zone_count,
            result.summary.status,
        )
        return result

    @staticmethod
    def _result_id(dataset: PreparedDataset, request: AnalysisRequest) -> str:
        identity = {
            "schema_version": "1.0",
            "dataset": request.dataset_id,
            "version": request.dataset_version,
            "processing": dataset.manifest.processing_version,
            "fingerprint": dataset.fingerprint,
            "bbox": [format(value, ".15g") for value in request.bbox],
            "from": request.start.isoformat(),
            "to": request.end.isoformat(),
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f"ar_{digest[:32]}"

    @staticmethod
    def _source_coverage(
        coverage_geometry: dict[str, Any] | None,
        bbox: BBox,
        query_area: float,
        dataset: PreparedDataset,
        valid_geometry: dict[str, Any] | None = None,
    ) -> SourceCoverage:
        if coverage_geometry is None:
            return SourceCoverage(status="none", covered_area_ha=None, valid_area_ha=None)
        clipped = clip_to_bbox(coverage_geometry, bbox)
        covered = geometry_area_ha(clipped, area_crs=dataset.manifest.area_crs) if clipped else 0.0
        valid = None
        if valid_geometry is not None:
            valid_clip = clip_to_bbox(valid_geometry, bbox)
            valid = (
                geometry_area_ha(valid_clip, area_crs=dataset.manifest.area_crs)
                if valid_clip
                else 0.0
            )
        return SourceCoverage(
            status=_coverage_status(covered, query_area),
            covered_area_ha=_rounded(covered),
            valid_area_ha=_rounded(valid) if valid is not None else None,
        )

    @staticmethod
    def _combined_coverage(
        dataset: PreparedDataset,
        bbox: BBox,
        query_area: float,
        active_fire: SourceCoverage,
        burn_scars: SourceCoverage,
    ) -> Coverage:
        geometries = [
            shape(value)
            for value in (dataset.manifest.af_coverage, dataset.manifest.bs_coverage)
            if value is not None
        ]
        covered = 0.0
        if geometries:
            union = mapping(unary_union(geometries))
            clipped = clip_to_bbox(union, bbox)
            if clipped:
                covered = geometry_area_ha(clipped, area_crs=dataset.manifest.area_crs)
        valid = burn_scars.valid_area_ha
        return Coverage(
            status=_coverage_status(covered, query_area),
            query_area_ha=_rounded(query_area),
            covered_area_ha=_rounded(covered),
            valid_area_ha=valid,
            active_fire=active_fire,
            burn_scars=burn_scars,
            method="Пересечение AOI с заявленными в manifest полигонами покрытия",
        )

    @staticmethod
    def _range(request: AnalysisRequest) -> tuple[datetime, datetime]:
        return (
            datetime.combine(request.start, time.min, tzinfo=UTC),
            datetime.combine(request.end + timedelta(days=1), time.min, tzinfo=UTC),
        )

    def _hotspots(
        self, dataset: PreparedDataset, request: AnalysisRequest, result_id: str
    ) -> list[Feature]:
        start, end = self._range(request)
        min_lon, min_lat, max_lon, max_lat = request.bbox
        selected: dict[str, Feature] = {}
        for raw in dataset.hotspots:
            props = dict(raw["properties"])
            acquired = datetime.fromisoformat(props["acquired_at"].replace("Z", "+00:00"))
            lon, lat = raw["geometry"]["coordinates"]
            if not (
                start <= acquired < end and min_lon <= lon <= max_lon and min_lat <= lat <= max_lat
            ):
                continue
            identifier = str(props.get("id") or raw["id"])
            props.update(
                {
                    "id": identifier,
                    "dataset_id": request.dataset_id,
                    "dataset_version": request.dataset_version,
                    "result_id": result_id,
                }
            )
            selected[identifier] = Feature(
                id=identifier, geometry=raw["geometry"], properties=props
            )
        return [selected[key] for key in sorted(selected)]

    def _burn_zones(
        self, dataset: PreparedDataset, request: AnalysisRequest, result_id: str
    ) -> tuple[list[Feature], set[str]]:
        start, end = self._range(request)
        candidates: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        assessment_time: dict[str, datetime] = {}
        for raw in dataset.burn_zones:
            props = raw["properties"]
            acquired = datetime.fromisoformat(props["after_acquired_at"].replace("Z", "+00:00"))
            if not start <= acquired < end or not props.get("is_complete", False):
                continue
            event_id = str(props["burn_event_id"])
            assessment_id = str(props["assessment_id"])
            candidates[event_id][assessment_id].append(raw)
            assessment_time[assessment_id] = acquired

        selected_raw: list[dict[str, Any]] = []
        for event_id in sorted(candidates):
            assessment_id = max(
                candidates[event_id], key=lambda item: (assessment_time[item], item)
            )
            selected_raw.extend(candidates[event_id][assessment_id])

        features: list[Feature] = []
        scene_ids: set[str] = set()
        clipped_geometries: list[dict[str, Any]] = []
        for raw in selected_raw:
            clipped = clip_to_bbox(raw["geometry"], request.bbox)
            if clipped is None:
                continue
            area = _rounded(geometry_area_ha(clipped, area_crs=dataset.manifest.area_crs))
            if area <= 0:
                continue
            props = dict(raw["properties"])
            source_id = str(props.get("id") or raw["id"])
            identifier = f"{source_id}:{result_id[-8:]}"
            props.update(
                {
                    "id": identifier,
                    "source_zone_id": source_id,
                    "contour_id": identifier,
                    "model_version": dataset.manifest.processing_version,
                    "source": props.get("source", dataset.manifest.origin),
                    "area_ha": area,
                    "dataset_id": request.dataset_id,
                    "dataset_version": request.dataset_version,
                    "result_id": result_id,
                    "origin": dataset.manifest.origin,
                    "processing_version": dataset.manifest.processing_version,
                }
            )
            scene_ids.update(str(value) for value in props.get("scene_ids", []))
            clipped_geometries.append(clipped)
            features.append(Feature(id=identifier, geometry=clipped, properties=props))
        assert_non_overlapping(clipped_geometries, area_crs=dataset.manifest.area_crs)
        features.sort(
            key=lambda feature: (
                str(feature.properties["burn_event_id"]),
                int(feature.properties["class_id"]),
                str(feature.id),
            )
        )
        return features, scene_ids

    @staticmethod
    def _warnings(
        dataset: PreparedDataset, active_fire: SourceCoverage, burn_scars: SourceCoverage
    ) -> list[AnalysisWarning]:
        warnings = []
        if dataset.manifest.origin == "synthetic_demo":
            warnings.append(
                AnalysisWarning(
                    code="synthetic_demo",
                    message=(
                        "Проверочный синтетический набор не подтверждает качество модели "
                        "на реальных сценах."
                    ),
                )
            )
        if active_fire.status != "full":
            warnings.append(
                AnalysisWarning(
                    code="active_fire_coverage",
                    message=(
                        "Покрытие термоточек отсутствует или охватывает только часть "
                        "выбранной области."
                    ),
                )
            )
        if burn_scars.status != "full":
            warnings.append(
                AnalysisWarning(
                    code="burn_scar_coverage",
                    message="Покрытие картирования гарей отсутствует или неполное.",
                )
            )
        if burn_scars.covered_area_ha and burn_scars.valid_area_ha == 0:
            warnings.append(
                AnalysisWarning(
                    code="no_valid_pixels",
                    message=(
                        "В покрытии гарей нет валидных пикселей; нули площади не рассчитываются."
                    ),
                )
            )
        elif (
            burn_scars.covered_area_ha
            and burn_scars.valid_area_ha is not None
            and burn_scars.valid_area_ha < burn_scars.covered_area_ha
        ):
            warnings.append(
                AnalysisWarning(
                    code="partial_valid_coverage",
                    message="Часть покрытия гарей исключена как nodata или невалидные пиксели.",
                )
            )
        return warnings

    @staticmethod
    def _summary(
        hotspots: list[Feature],
        zones: list[Feature],
        active_fire: SourceCoverage,
        burn_scars: SourceCoverage,
    ) -> AnalysisSummary:
        bs_available = burn_scars.status != "none" and (burn_scars.valid_area_ha or 0) > 0
        by_class = {class_id: 0.0 for class_id in SEVERITY}
        events: set[str] = set()
        for feature in zones:
            class_id = int(feature.properties["class_id"])
            by_class[class_id] += float(feature.properties["area_ha"])
            events.add(str(feature.properties["burn_event_id"]))
        if bs_available:
            by_class = {key: _rounded(value) for key, value in by_class.items()}
            total: float | None = _rounded(sum(by_class.values()))
        else:
            total = None
        severity = []
        for class_id, (code, label) in SEVERITY.items():
            area = by_class[class_id] if bs_available else None
            share = _rounded(area / total) if area is not None and total else None
            severity.append(
                SeveritySummary(
                    class_id=class_id,
                    label=label,
                    severity=code,
                    area_ha=area,
                    share=share,
                )
            )
        has_any_coverage = active_fire.status != "none" or burn_scars.status != "none"
        if zones or hotspots:
            status = "ok"
        elif not has_any_coverage:
            status = "no_coverage"
        elif (
            burn_scars.status != "none"
            and burn_scars.valid_area_ha == 0
            and active_fire.status == "none"
        ):
            status = "no_valid_data"
        else:
            status = "empty"
        return AnalysisSummary(
            status=status,
            hotspot_count=len(hotspots),
            burn_scar_count=len(events),
            zone_count=len(zones),
            total_burned_area_ha=total,
            severity=severity,
        )
