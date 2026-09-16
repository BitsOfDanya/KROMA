import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
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


@lru_cache
def get_settings() -> Settings:
    source = os.environ.get("KROMA_DATA_SOURCE", "demo")
    if source != "demo":
        raise RuntimeError(f"Unsupported KROMA_DATA_SOURCE: {source}")
    return Settings(
        data_source="demo",
        cors_origins=_split_csv(
            os.environ.get("KROMA_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        ),
        demo_anchor=_parse_anchor(os.environ.get("KROMA_DEMO_ANCHOR")),
    )
