import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

DataSource = Literal["demo"]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_anchor(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Settings:
    data_source: DataSource = "demo"
    cors_origins: list[str] = field(default_factory=list)
    demo_anchor: datetime | None = None
    firms_api_key: str | None = None
    firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    live_sources: tuple[str, ...] = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
    live_area: str = "world"
    live_day_range: int = 2
    live_refresh_seconds: int = 600
    live_cluster_radius_km: float = 6.0
    live_cluster_window_hours: float = 48.0
    live_retention_hours: float = 72.0
    prepared_data_path: Path = Path(__file__).resolve().parents[1] / "prepared_data"
    analysis_max_days: int = 366
    analysis_max_area_ha: float = 5_000_000
    analysis_max_features: int = 50_000


@lru_cache
def get_settings() -> Settings:
    source = os.environ.get("KROMA_DATA_SOURCE", "demo")
    if source != "demo":
        raise RuntimeError(f"Unsupported KROMA_DATA_SOURCE: {source}")
    prepared_data_path = os.environ.get("KROMA_PREPARED_DATA_PATH", "").strip()
    return Settings(
        data_source="demo",
        cors_origins=_split_csv(
            os.environ.get("KROMA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        ),
        demo_anchor=_parse_anchor(os.environ.get("KROMA_DEMO_ANCHOR")),
        firms_api_key=os.environ.get("NASA_FIRMS_API_KEY") or None,
        firms_base_url=os.environ.get(
            "KROMA_FIRMS_BASE_URL", "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
        ),
        live_sources=tuple(
            _split_csv(
                os.environ.get(
                    "KROMA_LIVE_SOURCES", "VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT"
                )
            )
        ),
        live_area=os.environ.get("KROMA_LIVE_AREA", "world"),
        live_day_range=int(os.environ.get("KROMA_LIVE_DAY_RANGE", "2")),
        live_refresh_seconds=int(os.environ.get("KROMA_LIVE_REFRESH_SECONDS", "600")),
        live_cluster_radius_km=float(os.environ.get("KROMA_LIVE_CLUSTER_RADIUS_KM", "6")),
        live_cluster_window_hours=float(os.environ.get("KROMA_LIVE_CLUSTER_WINDOW_HOURS", "48")),
        live_retention_hours=float(os.environ.get("KROMA_LIVE_RETENTION_HOURS", "72")),
        prepared_data_path=(
            Path(prepared_data_path)
            if prepared_data_path
            else Path(__file__).resolve().parents[1] / "prepared_data"
        ),
        analysis_max_days=int(os.environ.get("KROMA_ANALYSIS_MAX_DAYS", "366")),
        analysis_max_area_ha=float(
            os.environ.get("KROMA_ANALYSIS_MAX_AREA_HA", "5000000")
        ),
        analysis_max_features=int(os.environ.get("KROMA_ANALYSIS_MAX_FEATURES", "50000")),
    )
