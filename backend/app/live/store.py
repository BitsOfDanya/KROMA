import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.live.clustering import cluster_detections
from app.live.firms_client import fetch_all
from app.live.models import LiveDetection, LiveHealth, LiveIncident, LiveStatus


@dataclass
class _State:
    detections: list[LiveDetection] = field(default_factory=list)
    incidents: list[LiveIncident] = field(default_factory=list)
    last_fetch_at: datetime | None = None
    last_success_at: datetime | None = None
    error: str | None = None


class LiveStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._state = _State()
        self._lock = asyncio.Lock()

    async def refresh(self) -> None:
        settings = self.settings
        now = datetime.now(UTC)
        try:
            detections = await fetch_all(settings)
        except Exception as error:  # noqa: BLE001
            async with self._lock:
                self._state.last_fetch_at = now
                self._state.error = str(error)
            return
        cutoff = now - timedelta(hours=settings.live_retention_hours)
        async with self._lock:
            merged = {
                item.id: item for item in self._state.detections if item.acquired_at >= cutoff
            }
            for item in detections:
                merged[item.id] = item
            kept = [item for item in merged.values() if item.acquired_at >= cutoff]
            self._state.detections = kept
            self._state.incidents = cluster_detections(
                kept, settings.live_cluster_radius_km, settings.live_cluster_window_hours
            )
            self._state.last_fetch_at = now
            self._state.last_success_at = now
            self._state.error = None

    async def run_forever(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(self.settings.live_refresh_seconds)

    def detections(self) -> list[LiveDetection]:
        return list(self._state.detections)

    def incidents(self) -> list[LiveIncident]:
        return list(self._state.incidents)

    def status(self) -> LiveStatus:
        settings = self.settings
        state = self._state
        now = datetime.now(UTC)
        configured = settings.firms_api_key is not None
        health: LiveHealth
        if not configured:
            health = "offline"
        elif state.last_success_at is None:
            health = "offline"
        else:
            age_seconds = (now - state.last_success_at).total_seconds()
            if age_seconds <= settings.live_refresh_seconds:
                health = "live"
            elif age_seconds <= settings.live_refresh_seconds * 4:
                health = "nrt"
            else:
                health = "stale"
        latest_observation_at = (
            max((item.acquired_at for item in state.detections), default=None)
            if state.detections
            else None
        )
        next_refresh_at = (
            state.last_fetch_at + timedelta(seconds=settings.live_refresh_seconds)
            if state.last_fetch_at
            else None
        )
        error = state.error
        if not configured:
            error = "NASA_FIRMS_API_KEY не задан"
        return LiveStatus(
            source="NASA FIRMS (VIIRS)",
            status=health,
            configured=configured,
            last_fetch_at=state.last_success_at,
            latest_observation_at=latest_observation_at,
            next_refresh_at=next_refresh_at,
            refresh_interval_seconds=settings.live_refresh_seconds,
            detection_count=len(state.detections),
            incident_count=len(state.incidents),
            error=error,
        )
