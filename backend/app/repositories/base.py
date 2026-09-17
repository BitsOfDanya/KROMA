from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models.burn_scar import BurnScar
from app.models.context import (
    CloudField,
    Region,
    RiskObject,
    RiskObjectKind,
    WeeklyStat,
    WindSample,
)
from app.models.geometry import BBox
from app.models.incident import ForecastZone, Incident, PerimeterState, TimelineEvent
from app.models.observation import Observation, ObservationClass, SatellitePass, ThermalSource


@dataclass(frozen=True)
class ObservationQuery:
    incident_id: str | None = None
    bbox: BBox | None = None
    start: datetime | None = None
    end: datetime | None = None
    classifications: tuple[ObservationClass, ...] | None = None


class FireDataRepository(Protocol):
    def reference_time(self) -> datetime: ...

    def regions(self) -> list[Region]: ...

    def incidents(self) -> list[Incident]: ...

    def incident(self, incident_id: str) -> Incident | None: ...

    def perimeters(self, incident_id: str | None = None) -> list[PerimeterState]: ...

    def forecasts(self, incident_id: str) -> list[ForecastZone]: ...

    def observations(self, query: ObservationQuery) -> list[Observation]: ...

    def timeline(
        self, incident_id: str | None, start: datetime | None, end: datetime | None
    ) -> list[TimelineEvent]: ...

    def satellite_passes(self, incident_id: str) -> list[SatellitePass]: ...

    def thermal_sources(self, bbox: BBox | None) -> list[ThermalSource]: ...

    def risk_objects(
        self, bbox: BBox | None, kinds: tuple[RiskObjectKind, ...] | None = None
    ) -> list[RiskObject]: ...

    def burn_scars(self) -> list[BurnScar]: ...

    def burn_scar(self, burn_scar_id: str) -> BurnScar | None: ...

    def wind(self, bbox: BBox | None) -> list[WindSample]: ...

    def clouds(self, bbox: BBox | None) -> list[CloudField]: ...

    def weekly_stats(self) -> list[WeeklyStat]: ...
