from typing import Any

from kroma_ml.incidents import Incident, Observation
from kroma_ml.thermal_memory import ThermalProfile


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def incident_features(
    incident: Incident,
    observations: list[Observation],
    thermal_memory: ThermalProfile | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ids = set(incident.observation_ids)
    members = [item for item in observations if item.observation_id in ids]
    if len(members) != incident.observation_count:
        raise ValueError("observations do not match incident")
    viirs = [item for item in members if item.source.startswith("VIIRS")]
    modis = [item for item in members if item.source.startswith("MODIS")]
    night = [item for item in members if item.daynight in {"D", "N"}]
    viirs_confidence = [
        item.source_confidence for item in viirs if item.source_confidence in {"l", "n", "h"}
    ]
    modis_confidence = [
        float(item.source_confidence)
        for item in modis
        if isinstance(item.source_confidence, int | float)
    ]
    context = context or {}
    return {
        "incident_id": incident.incident_id,
        "region": incident.region,
        "month": incident.first_seen.month,
        "observation_count": incident.observation_count,
        "sensor_count": incident.sensor_count,
        "duration_hours": (incident.last_seen - incident.first_seen).total_seconds() / 3600,
        "extent_radius_km": incident.extent_radius_km,
        "max_frp_mw": incident.max_frp_mw,
        "mean_frp_mw": incident.mean_frp_mw,
        "frp_trend_mw_per_day": incident.frp_trend_mw_per_day,
        "night_ratio": night.count("N") / len(night) if night else None,
        "viirs_high_ratio": (
            viirs_confidence.count("h") / len(viirs_confidence) if viirs_confidence else None
        ),
        "viirs_low_ratio": (
            viirs_confidence.count("l") / len(viirs_confidence) if viirs_confidence else None
        ),
        "modis_native_confidence_mean": _mean(modis_confidence),
        "viirs_brightness_mean_kelvin": _mean(
            [item.brightness_kelvin for item in viirs if item.brightness_kelvin is not None]
        ),
        "modis_brightness_mean_kelvin": _mean(
            [item.brightness_kelvin for item in modis if item.brightness_kelvin is not None]
        ),
        "scan_mean_km": _mean([item.scan_km for item in members if item.scan_km is not None]),
        "track_mean_km": _mean([item.track_km for item in members if item.track_km is not None]),
        "historical_active_days": thermal_memory.active_days if thermal_memory else None,
        "historical_detection_count": (
            thermal_memory.historical_detection_count if thermal_memory else None
        ),
        "thermal_novelty_score": (thermal_memory.thermal_novelty_score if thermal_memory else None),
        "land_cover": context.get("land_cover"),
        "distance_to_settlement_km": context.get("distance_to_settlement_km"),
        "distance_to_road_km": context.get("distance_to_road_km"),
        "distance_to_power_line_km": context.get("distance_to_power_line_km"),
        "distance_to_industrial_km": context.get("distance_to_industrial_km"),
        "distance_to_airport_km": context.get("distance_to_airport_km"),
        "distance_to_railway_km": context.get("distance_to_railway_km"),
        "protected_area_intersection": context.get("protected_area_intersection"),
        "wind_speed_ms": context.get("wind_speed_ms"),
        "relative_humidity": context.get("relative_humidity"),
        "precipitation_mm": context.get("precipitation_mm"),
    }
