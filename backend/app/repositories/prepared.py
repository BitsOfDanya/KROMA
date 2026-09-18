from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.analysis import PreparedDatasetManifest
from app.services.errors import DatasetUnavailableError, NotFoundError
from kroma_geo.vector import GeometryError, assert_non_overlapping, validate_geometry
from pydantic import ValidationError


@dataclass(frozen=True)
class PreparedDataset:
    manifest: PreparedDatasetManifest
    hotspots: tuple[dict[str, Any], ...]
    burn_zones: tuple[dict[str, Any], ...]
    fingerprint: str
    root: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatasetUnavailableError(
            f"Dataset artifact {path.name} is not readable JSON"
        ) from error


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise DatasetUnavailableError(f"{field} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DatasetUnavailableError(f"{field} must be an ISO datetime") from error
    if parsed.tzinfo is None:
        raise DatasetUnavailableError(f"{field} must include a timezone")
    return parsed


class PreparedDatasetRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._datasets: dict[tuple[str, str], PreparedDataset] = {}
        self._errors: list[str] = []
        self._load_all()

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def _manifest_paths(self) -> list[Path]:
        if self.root.is_file():
            return [self.root]
        direct = self.root / "manifest.json"
        paths = [direct] if direct.is_file() else []
        if self.root.is_dir():
            paths.extend(
                sorted(path for path in self.root.glob("*/manifest.json") if path != direct)
            )
        return paths

    def _load_all(self) -> None:
        paths = self._manifest_paths()
        if not paths:
            self._errors.append("No prepared dataset manifest.json found")
            return
        for path in paths:
            try:
                dataset = self._load(path)
            except DatasetUnavailableError as error:
                self._errors.append(f"{path.name}: {error}")
                continue
            key = (dataset.manifest.dataset_id, dataset.manifest.dataset_version)
            if key in self._datasets:
                self._errors.append(f"Duplicate prepared dataset {key[0]}@{key[1]}")
                continue
            self._datasets[key] = dataset

    def _load(self, manifest_path: Path) -> PreparedDataset:
        raw_manifest = _read_json(manifest_path)
        try:
            manifest = PreparedDatasetManifest.model_validate(raw_manifest)
        except ValidationError as error:
            raise DatasetUnavailableError("Manifest does not match schema") from error
        root = manifest_path.parent
        loaded: dict[str, Any] = {}
        fingerprints: list[str] = [_sha256(manifest_path)]
        for name, artifact in manifest.artifacts.items():
            path = (root / artifact.path).resolve()
            try:
                path.relative_to(root.resolve())
            except ValueError as error:
                raise DatasetUnavailableError(
                    f"Artifact {name} escapes dataset directory"
                ) from error
            if not path.is_file():
                raise DatasetUnavailableError(f"Artifact {name} is missing")
            actual = _sha256(path)
            if actual != artifact.sha256:
                raise DatasetUnavailableError(f"Checksum mismatch for artifact {name}")
            fingerprints.append(actual)
            loaded[name] = _read_json(path)

        hotspots = self._features(loaded["hotspots"], "hotspots")
        zones = self._features(loaded["burn_zones"], "burn_zones")
        self._validate_hotspots(hotspots)
        self._validate_zones(zones, manifest)
        for coverage in (manifest.af_coverage, manifest.bs_coverage, manifest.bs_valid_coverage):
            if coverage is not None:
                try:
                    validate_geometry(coverage)
                except GeometryError as error:
                    raise DatasetUnavailableError(f"Invalid coverage geometry: {error}") from error
        fingerprint = hashlib.sha256("|".join(fingerprints).encode()).hexdigest()
        return PreparedDataset(manifest, tuple(hotspots), tuple(zones), fingerprint, root)

    @staticmethod
    def _features(value: Any, name: str) -> list[dict[str, Any]]:
        if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
            raise DatasetUnavailableError(f"{name} must be a GeoJSON FeatureCollection")
        features = value.get("features")
        if not isinstance(features, list):
            raise DatasetUnavailableError(f"{name}.features must be an array")
        return features

    @staticmethod
    def _validate_hotspots(features: list[dict[str, Any]]) -> None:
        seen: set[str] = set()
        for feature in features:
            props = feature.get("properties", {})
            identifier = str(props.get("id") or feature.get("id") or "")
            if not identifier or identifier in seen:
                raise DatasetUnavailableError("Hotspot IDs must be present and unique")
            seen.add(identifier)
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [])
            if geometry.get("type") != "Point" or len(coordinates) != 2:
                raise DatasetUnavailableError(f"Hotspot {identifier} must be a Point")
            lon, lat = coordinates
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise DatasetUnavailableError(f"Hotspot {identifier} is outside WGS84")
            _parse_time(props.get("acquired_at"), f"hotspot {identifier}.acquired_at")

    @staticmethod
    def _validate_zones(features: list[dict[str, Any]], manifest: PreparedDatasetManifest) -> None:
        seen: set[str] = set()
        by_assessment: dict[str, list[dict[str, Any]]] = {}
        assessment_event: dict[str, str] = {}
        expected_severity = {1: "low", 2: "moderate", 3: "high"}
        for feature in features:
            props = feature.get("properties", {})
            identifier = str(props.get("id") or feature.get("id") or "")
            if not identifier or identifier in seen:
                raise DatasetUnavailableError("Burn-zone IDs must be present and unique")
            seen.add(identifier)
            class_id = props.get("class_id")
            if (
                class_id not in expected_severity
                or props.get("severity") != expected_severity[class_id]
            ):
                raise DatasetUnavailableError(f"Zone {identifier} has invalid class/severity")
            event_id = props.get("burn_event_id")
            assessment_id = props.get("assessment_id")
            if not isinstance(event_id, str) or not isinstance(assessment_id, str):
                raise DatasetUnavailableError(f"Zone {identifier} lacks event/assessment IDs")
            previous = assessment_event.setdefault(assessment_id, event_id)
            if previous != event_id:
                raise DatasetUnavailableError(
                    f"Assessment {assessment_id} belongs to multiple events"
                )
            _parse_time(props.get("after_acquired_at"), f"zone {identifier}.after_acquired_at")
            try:
                validate_geometry(feature.get("geometry", {}))
            except GeometryError as error:
                raise DatasetUnavailableError(f"Zone {identifier}: {error}") from error
            by_assessment.setdefault(assessment_id, []).append(feature["geometry"])
        try:
            for geometries in by_assessment.values():
                assert_non_overlapping(geometries, area_crs=manifest.area_crs)
        except GeometryError as error:
            raise DatasetUnavailableError(str(error)) from error

    def list(self) -> list[PreparedDataset]:
        return [self._datasets[key] for key in sorted(self._datasets)]

    def get(self, dataset_id: str, dataset_version: str) -> PreparedDataset:
        dataset = self._datasets.get((dataset_id, dataset_version))
        if dataset is None:
            raise NotFoundError("prepared dataset", f"{dataset_id}@{dataset_version}")
        return dataset


@lru_cache
def get_prepared_repository() -> PreparedDatasetRepository:
    return PreparedDatasetRepository(get_settings().prepared_data_path)
