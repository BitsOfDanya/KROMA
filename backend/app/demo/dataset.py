import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from kroma_geo.measure import bbox_of, destination, polygon_area_ha, ring_centroid

from app.demo import catalog
from app.demo.shapes import (
    ShapeNoise,
    active_front,
    blob,
    fire_perimeter,
    nested_zone,
    sample_in_ring,
    scatter_around,
)
from app.models.burn_scar import BurnScar, ImageryScene, SeverityZone
from app.models.context import CloudField, Region, RiskObject, WeeklyStat, WindSample
from app.models.geometry import LineGeometry, PointGeometry, PolygonGeometry, Position, Ring
from app.models.incident import (
    EvidenceItem,
    ForecastZone,
    Incident,
    IncidentSnapshot,
    PerimeterState,
    SpreadEstimate,
    TimelineEvent,
)
from app.models.observation import Observation, SatellitePass, ThermalSource

SEVERITY_BANDS = ((85, "критический"), (65, "высокий"), (40, "средний"), (0, "низкий"))


@dataclass
class DemoDataset:
    anchor: datetime
    regions: list[Region] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    perimeters: list[PerimeterState] = field(default_factory=list)
    forecasts: list[ForecastZone] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    passes: list[SatellitePass] = field(default_factory=list)
    thermal_sources: list[ThermalSource] = field(default_factory=list)
    risk_objects: list[RiskObject] = field(default_factory=list)
    burn_scars: list[BurnScar] = field(default_factory=list)
    wind: list[WindSample] = field(default_factory=list)
    clouds: list[CloudField] = field(default_factory=list)
    weekly_stats: list[WeeklyStat] = field(default_factory=list)


def _observation_id(source: str, acquired_at: datetime, location: Position) -> str:
    identity = f"{source}|{acquired_at.isoformat()}|{location[0]:.5f}|{location[1]:.5f}"
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _band(priority: int) -> str:
    return next(label for threshold, label in SEVERITY_BANDS if priority >= threshold)


def _is_day(acquired_at: datetime, lon: float) -> bool:
    local_hour = (acquired_at.hour + acquired_at.minute / 60 + lon / 15) % 24
    return 7 <= local_hour <= 19


def _pixels_label(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} пиксель"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} пикселя"
    return f"{count} пикселей"


def _source_label(satellite: str) -> str:
    return f"{satellite} {catalog.SATELLITES[satellite].instrument}"


def _pass_time(day: date, lon: float, local_solar_hour: float) -> datetime:
    utc_hours = (local_solar_hour - lon / 15) % 24
    base = datetime.combine(day, time(0, 0), tzinfo=UTC)
    return base + timedelta(hours=utc_hours)


class DatasetBuilder:
    def __init__(self, anchor: datetime) -> None:
        self.anchor = anchor.astimezone(UTC).replace(second=0, microsecond=0)
        self.data = DemoDataset(anchor=self.anchor, regions=list(catalog.REGIONS))

    def build(self) -> DemoDataset:
        self._build_risk_objects()
        for spec in catalog.INCIDENTS:
            self._build_incident(spec)
        self._build_thermal_sources()
        self._build_background_detections()
        self._build_burn_scars()
        self._build_environment()
        self._build_weekly_stats()
        self.data.observations.sort(key=lambda item: item.acquired_at)
        self.data.timeline.sort(key=lambda item: item.occurred_at)
        self.data.passes.sort(key=lambda item: item.overpass_at)
        return self.data

    def _ago(self, hours: float) -> datetime:
        return self.anchor - timedelta(minutes=round(hours * 60))

    def _build_risk_objects(self) -> None:
        objects = self.data.risk_objects
        for settlement in catalog.SETTLEMENTS:
            objects.append(
                RiskObject(
                    id=settlement.id,
                    kind="settlement",
                    name=settlement.name,
                    subtitle=settlement.kind,
                    region_id=settlement.region_id,
                    population=settlement.population,
                    geometry=PointGeometry(coordinates=settlement.location),
                )
            )
        for linear in catalog.LINEAR_OBJECTS:
            objects.append(
                RiskObject(
                    id=linear.id,
                    kind=linear.kind,
                    name=linear.name,
                    subtitle=linear.subtitle,
                    region_id=linear.region_id,
                    geometry=LineGeometry(coordinates=list(linear.coordinates)),
                )
            )
        for point in catalog.INFRASTRUCTURE:
            objects.append(
                RiskObject(
                    id=point.id,
                    kind="infrastructure",
                    name=point.name,
                    subtitle=point.subtitle,
                    region_id=point.region_id,
                    geometry=PointGeometry(coordinates=point.location),
                )
            )
        for area in catalog.PROTECTED_AREAS:
            ring = blob(
                area.center,
                area.area_ha,
                ShapeNoise.seeded(area.seed, 1.4),
                area.elongation,
                area.axis_deg,
            )
            objects.append(
                RiskObject(
                    id=area.id,
                    kind="protected_area",
                    name=area.name,
                    subtitle=area.subtitle,
                    region_id=area.region_id,
                    geometry=PolygonGeometry(coordinates=[ring]),
                )
            )

    def _build_incident(self, spec: catalog.IncidentSpec) -> None:
        rng = random.Random(spec.seed)
        noise = ShapeNoise.seeded(spec.seed)
        snapshots: list[IncidentSnapshot] = []
        rings: list[Ring] = []
        observation_total = 0
        confirmed_at: datetime | None = None
        previous_band: str | None = None
        previous_status = None
        stage_times = [self._ago(stage.hours_ago) for stage in spec.stages]

        for index, stage in enumerate(spec.stages):
            observed_at = stage_times[index]
            ring = fire_perimeter(
                spec.ignition, spec.direction_deg, stage.area_ha, spec.eccentricity, noise
            )
            rings.append(ring)
            satellite = catalog.SATELLITES[stage.satellite]
            points = sample_in_ring(rng, ring, stage.pixels, spec.ignition, spec.direction_deg) or [
                spec.ignition
            ]
            for point in points:
                frp_share = stage.frp_mw / max(len(points), 1)
                acquired_at = observed_at + timedelta(seconds=rng.randint(0, 50))
                self.data.observations.append(
                    Observation(
                        id=_observation_id(satellite.source, acquired_at, point),
                        incident_id=spec.id,
                        classification="incident",
                        source=satellite.source,
                        satellite=stage.satellite,
                        instrument=satellite.instrument,
                        acquired_at=acquired_at,
                        location=point,
                        frp_mw=round(frp_share * rng.uniform(0.55, 1.6), 1),
                        brightness_k=round(rng.uniform(330, 367), 1),
                        source_confidence="h" if rng.random() < 0.55 else "n",
                        daynight="D" if _is_day(acquired_at, point[0]) else "N",
                        pixel_size_m=satellite.pixel_size_m,
                    )
                )
            observation_total += len(points)
            snapshots.append(
                IncidentSnapshot(
                    observed_at=observed_at,
                    status=stage.status,
                    confidence=stage.confidence,
                    threat=stage.threat,
                    priority=stage.priority,
                    area_ha=round(polygon_area_ha([ring])),
                    frp_mw=stage.frp_mw,
                    observation_count=observation_total,
                )
            )

            detail = (
                f"{stage.satellite} {satellite.instrument} · {_pixels_label(len(points))}, "
                f"FRP {stage.frp_mw:.0f} МВт"
            )
            if index == 0:
                self._event(spec.id, observed_at, "detected", "Первое обнаружение", detail)
            else:
                self._event(spec.id, observed_at, "observation", "Повторное наблюдение", detail)
                self._event(
                    spec.id,
                    observed_at + timedelta(minutes=6),
                    "perimeter_updated",
                    "Обновлён периметр",
                    f"Оценка площади {snapshots[-1].area_ha:,.0f} га".replace(",", " "),
                )
            if stage.status == "confirmed" and confirmed_at is None:
                confirmed_at = observed_at + timedelta(minutes=4)
                self._event(
                    spec.id,
                    confirmed_at,
                    "confirmed",
                    "Событие подтверждено",
                    f"Confidence {stage.confidence}, повторное наблюдение",
                )
            band = _band(stage.priority)
            if previous_band is not None and band != previous_band:
                self._event(
                    spec.id,
                    observed_at + timedelta(minutes=5),
                    "priority_changed",
                    f"Приоритет: {band}",
                    f"Priority {spec.stages[index - 1].priority} → {stage.priority}",
                )
            if (
                previous_status is not None
                and stage.status != previous_status
                and stage.status
                in (
                    "monitoring",
                    "localized",
                )
            ):
                title = "Переведён в наблюдение" if stage.status == "monitoring" else "Локализован"
                self._event(
                    spec.id, observed_at + timedelta(minutes=8), "status_changed", title, ""
                )
            previous_band = band
            previous_status = stage.status

        for index, ring in enumerate(rings):
            valid_until = stage_times[index + 1] if index + 1 < len(rings) else None
            front = active_front(ring, spec.ignition, spec.direction_deg)
            if spec.stages[index].status == "localized":
                front = []
            self.data.perimeters.append(
                PerimeterState(
                    incident_id=spec.id,
                    observed_at=stage_times[index],
                    valid_until=valid_until,
                    source=_source_label(spec.stages[index].satellite),
                    area_ha=snapshots[index].area_ha,
                    perimeter=PolygonGeometry(coordinates=[ring]),
                    active_front=LineGeometry(coordinates=front),
                )
            )

        final = spec.stages[-1]
        current_ring = rings[-1]
        issued_at = stage_times[-1] + timedelta(minutes=12)
        if final.status in ("confirmed", "monitoring"):
            for level in catalog.FORECAST_LEVELS:
                forecast_noise = ShapeNoise.seeded(spec.seed + len(level.level) * 17, 0.8)
                ring = fire_perimeter(
                    spec.ignition,
                    spec.direction_deg,
                    snapshots[-1].area_ha * level.area_multiplier,
                    min(0.9, spec.eccentricity + level.eccentricity_delta),
                    forecast_noise,
                )
                self.data.forecasts.append(
                    ForecastZone(
                        id=f"{spec.id}-{level.level}",
                        incident_id=spec.id,
                        level=level.level,
                        issued_at=issued_at,
                        horizon_hours=24,
                        area_ha=round(polygon_area_ha([ring])),
                        geometry=PolygonGeometry(coordinates=[ring]),
                    )
                )
            self._event(
                spec.id,
                issued_at,
                "forecast_issued",
                "Прогноз распространения",
                "Горизонт 24 ч, коридоры P50 / P80 / P95",
            )
        if spec.id == catalog.SHOWCASE_INCIDENT_ID:
            self._event(
                spec.id,
                self._ago(9.4),
                "weather_updated",
                "Смена ветра",
                "ЮВ 7 м/с — направление на Кодинск",
            )

        self.data.incidents.append(
            Incident(
                id=spec.id,
                status=final.status,
                region_id=spec.region_id,
                region=catalog.REGION_NAMES[spec.region_id],
                district=spec.district,
                centroid=ring_centroid(current_ring),
                ignition_point=spec.ignition,
                first_detected_at=stage_times[0],
                confirmed_at=confirmed_at,
                updated_at=self.anchor - timedelta(minutes=spec.updated_minutes_ago),
                landcover=spec.landcover,
                spread=SpreadEstimate(
                    direction_deg=spec.direction_deg,
                    speed_m_per_h=spec.spread_speed_m_per_h,
                    wind_from_deg=(spec.direction_deg + 180) % 360,
                    wind_speed_ms=spec.wind_speed_ms,
                ),
                snapshots=snapshots,
                evidence=[
                    EvidenceItem(
                        code=item.code,
                        label=item.label,
                        detail=item.detail,
                        effect=item.effect,
                        strength=item.strength,
                    )
                    for item in spec.evidence
                ],
                burn_scar_id=spec.burn_scar_id,
            )
        )
        self._build_passes(spec, stage_times, rng)

    def _event(
        self, incident_id: str | None, occurred_at: datetime, kind: str, title: str, detail: str
    ) -> None:
        index = len(self.data.timeline) + 1
        self.data.timeline.append(
            TimelineEvent(
                id=f"EV-{index:05d}",
                incident_id=incident_id,
                occurred_at=occurred_at,
                kind=kind,
                title=title,
                detail=detail,
            )
        )

    def _build_passes(
        self, spec: catalog.IncidentSpec, stage_times: list[datetime], rng: random.Random
    ) -> None:
        lon, lat = spec.ignition
        coverage = (lon - 12, lat - 6, lon + 12, lat + 6)
        for index, stage in enumerate(spec.stages):
            satellite = catalog.SATELLITES[stage.satellite]
            self.data.passes.append(
                SatellitePass(
                    id=f"{spec.id}-past-{index}",
                    incident_id=spec.id,
                    satellite=stage.satellite,
                    instrument=satellite.instrument,
                    kind="thermal",
                    resolution_m=satellite.pixel_size_m,
                    overpass_at=stage_times[index],
                    cloud_probability=rng.randint(5, 40),
                    coverage=coverage,
                )
            )

        if spec.id == catalog.SHOWCASE_INCIDENT_ID:
            upcoming = [
                ("NOAA-21", "VIIRS", "thermal", 375, 38, 18),
                ("Suomi NPP", "VIIRS", "thermal", 375, 92, 24),
                ("Aqua", "MODIS", "thermal", 1000, 171, 35),
                ("Sentinel-2B", "MSI", "optical", 10, 17 * 60 + 5, 72),
                ("NOAA-20", "VIIRS", "thermal", 375, 11 * 60 + 40, 51),
                ("Landsat 9", "OLI/TIRS", "optical", 30, 41 * 60 + 20, 44),
            ]
            for index, (name, instrument, kind, resolution, minutes, cloud) in enumerate(upcoming):
                self.data.passes.append(
                    SatellitePass(
                        id=f"{spec.id}-next-{index}",
                        incident_id=spec.id,
                        satellite=name,
                        instrument=instrument,
                        kind=kind,
                        resolution_m=resolution,
                        overpass_at=self.anchor + timedelta(minutes=minutes),
                        cloud_probability=cloud,
                        coverage=coverage,
                    )
                )
            return

        schedule = [
            ("Suomi NPP", "VIIRS", "thermal", 375, 13.4),
            ("Suomi NPP", "VIIRS", "thermal", 375, 1.4),
            ("NOAA-20", "VIIRS", "thermal", 375, 12.6),
            ("NOAA-21", "VIIRS", "thermal", 375, 14.2),
            ("Aqua", "MODIS", "thermal", 1000, 13.5),
            ("Terra", "MODIS", "thermal", 1000, 22.5),
            ("Sentinel-2A", "MSI", "optical", 10, 10.5),
            ("Landsat 8", "OLI/TIRS", "optical", 30, 10.2),
        ]
        horizon = self.anchor + timedelta(hours=48)
        for day_offset in range(0, 3):
            day = (self.anchor + timedelta(days=day_offset)).date()
            for name, instrument, kind, resolution, local_hour in schedule:
                if kind == "optical" and rng.random() < 0.6:
                    continue
                overpass = _pass_time(day, lon, local_hour) + timedelta(
                    minutes=rng.randint(-25, 25)
                )
                if not self.anchor < overpass <= horizon:
                    continue
                self.data.passes.append(
                    SatellitePass(
                        id=f"{spec.id}-next-{day_offset}-{name}-{local_hour}",
                        incident_id=spec.id,
                        satellite=name,
                        instrument=instrument,
                        kind=kind,
                        resolution_m=resolution,
                        overpass_at=overpass,
                        cloud_probability=rng.randint(8, 90),
                        coverage=coverage,
                    )
                )

    def _build_thermal_sources(self) -> None:
        rng = random.Random(7)
        satellites = list(catalog.SATELLITES)
        for spec in catalog.THERMAL_SOURCES:
            detections = 0
            last_seen = self.anchor - timedelta(days=7)
            for day_offset in range(7, -1, -1):
                day = (self.anchor - timedelta(days=day_offset)).date()
                for _ in range(spec.daily_detections):
                    local_hour = rng.choice((1.4, 13.4, 12.6, 14.2, 22.5))
                    acquired_at = _pass_time(day, spec.location[0], local_hour) + timedelta(
                        minutes=rng.randint(-20, 20)
                    )
                    if acquired_at > self.anchor:
                        continue
                    point = scatter_around(rng, spec.location, 0.4, 1)[0]
                    satellite_name = rng.choice(satellites)
                    satellite = catalog.SATELLITES[satellite_name]
                    self.data.observations.append(
                        Observation(
                            id=_observation_id(satellite.source, acquired_at, point),
                            incident_id=None,
                            classification="persistent_source",
                            source=satellite.source,
                            satellite=satellite_name,
                            instrument=satellite.instrument,
                            acquired_at=acquired_at,
                            location=point,
                            frp_mw=round(spec.mean_frp_mw * rng.uniform(0.6, 1.4), 1),
                            brightness_k=round(rng.uniform(320, 350), 1),
                            source_confidence="n",
                            daynight="D" if _is_day(acquired_at, point[0]) else "N",
                            pixel_size_m=satellite.pixel_size_m,
                        )
                    )
                    detections += 1
                    last_seen = max(last_seen, acquired_at)
            self.data.thermal_sources.append(
                ThermalSource(
                    id=spec.id,
                    name=spec.name,
                    kind=spec.kind,
                    location=spec.location,
                    observation_count=spec.observation_count + detections,
                    history_years=spec.history_years,
                    first_seen_at=self.anchor - timedelta(days=round(spec.history_years * 365)),
                    last_seen_at=last_seen,
                    mean_frp_mw=spec.mean_frp_mw,
                )
            )

    def _build_background_detections(self) -> None:
        satellites = list(catalog.SATELLITES)
        for cluster in catalog.BACKGROUND_DETECTIONS:
            rng = random.Random(cluster.seed)
            for point in scatter_around(rng, cluster.center, cluster.radius_km, cluster.count):
                hours_ago = rng.uniform(0.3, 7 * 24)
                day = (self.anchor - timedelta(hours=hours_ago)).date()
                local_hour = rng.choice((1.4, 13.4, 12.6, 14.2, 13.5, 22.5, 10.5))
                acquired_at = _pass_time(day, point[0], local_hour) + timedelta(
                    minutes=rng.randint(-30, 30)
                )
                if acquired_at > self.anchor:
                    acquired_at -= timedelta(days=1)
                satellite_name = rng.choice(satellites)
                satellite = catalog.SATELLITES[satellite_name]
                high = rng.random() < cluster.high_share
                self.data.observations.append(
                    Observation(
                        id=_observation_id(satellite.source, acquired_at, point),
                        incident_id=None,
                        classification="unassigned",
                        source=satellite.source,
                        satellite=satellite_name,
                        instrument=satellite.instrument,
                        acquired_at=acquired_at,
                        location=point,
                        frp_mw=round(rng.lognormvariate(1.8, 0.7), 1),
                        brightness_k=round(rng.uniform(302, 345), 1),
                        source_confidence="h" if high else rng.choice(("l", "n", "n")),
                        daynight="D" if _is_day(acquired_at, point[0]) else "N",
                        pixel_size_m=satellite.pixel_size_m,
                    )
                )

    def _build_burn_scars(self) -> None:
        for spec in catalog.BURN_SCARS:
            total = spec.low_ha + spec.moderate_ha + spec.high_ha
            outer = blob(
                spec.center,
                total,
                ShapeNoise.seeded(spec.seed, 1.5),
                spec.elongation,
                spec.axis_deg,
            )
            burned = nested_zone(
                outer,
                spec.center,
                spec.moderate_ha + spec.high_ha,
                ShapeNoise.seeded(spec.seed + 1),
            )
            core = nested_zone(burned, spec.center, spec.high_ha, ShapeNoise.seeded(spec.seed + 2))
            self.data.burn_scars.append(
                self._burn_scar(
                    spec_id=spec.id,
                    incident_id=None,
                    name=spec.name,
                    region_id=spec.region_id,
                    district=spec.district,
                    outer=outer,
                    zones=((spec.low_ha, outer), (spec.moderate_ha, burned), (spec.high_ha, core)),
                    fire_started_on=spec.fire_started_on,
                    fire_ended_on=spec.fire_ended_on,
                    assessed_at=datetime.combine(spec.after_on, time(9, 30), tzinfo=UTC)
                    + timedelta(days=1),
                    assessment="final",
                    landcover=spec.landcover,
                    before_on=spec.before_on,
                    after_on=spec.after_on,
                    seed=spec.seed,
                )
            )

        showcase = next(
            item for item in catalog.INCIDENTS if item.id == catalog.SHOWCASE_INCIDENT_ID
        )
        noise = ShapeNoise.seeded(showcase.seed)
        area_total = 1050
        outer = fire_perimeter(
            showcase.ignition, showcase.direction_deg, area_total, showcase.eccentricity, noise
        )
        burned = fire_perimeter(
            showcase.ignition, showcase.direction_deg, 610, showcase.eccentricity - 0.04, noise
        )
        core = fire_perimeter(
            showcase.ignition, showcase.direction_deg, 240, showcase.eccentricity - 0.1, noise
        )
        assessed = self._ago(5.6)
        self.data.burn_scars.append(
            self._burn_scar(
                spec_id=showcase.burn_scar_id or "BS-2026-116",
                incident_id=showcase.id,
                name="Гарь KR-042, предварительная",
                region_id=showcase.region_id,
                district=showcase.district,
                outer=outer,
                zones=(
                    (round(polygon_area_ha([outer]) - polygon_area_ha([burned])), outer),
                    (round(polygon_area_ha([burned]) - polygon_area_ha([core])), burned),
                    (round(polygon_area_ha([core])), core),
                ),
                fire_started_on=self._ago(19.2).date(),
                fire_ended_on=None,
                assessed_at=assessed,
                assessment="preliminary",
                landcover=showcase.landcover,
                before_on=(self.anchor - timedelta(days=8)).date(),
                after_on=(assessed - timedelta(minutes=50)).date(),
                seed=showcase.seed,
            )
        )
        self.data.burn_scars.sort(key=lambda item: item.area_ha, reverse=True)

    def _burn_scar(
        self,
        *,
        spec_id: str,
        incident_id: str | None,
        name: str,
        region_id: str,
        district: str,
        outer: Ring,
        zones: tuple[tuple[float, Ring], ...],
        fire_started_on: date,
        fire_ended_on: date | None,
        assessed_at: datetime,
        assessment: str,
        landcover: str,
        before_on: date,
        after_on: date,
        seed: int,
    ) -> BurnScar:
        rng = random.Random(seed * 3)
        severity_names = ("low", "moderate", "high")
        area = sum(zone[0] for zone in zones)
        high_share = zones[2][0] / area
        tile = f"T{46 + int(outer[0][0] // 6)}V{'UV'[rng.randint(0, 1)]}{'CDE'[rng.randint(0, 2)]}"
        return BurnScar(
            id=spec_id,
            incident_id=incident_id,
            name=name,
            region_id=region_id,
            region=catalog.REGION_NAMES[region_id],
            district=district,
            centroid=ring_centroid(outer),
            bbox=bbox_of(outer),
            fire_started_on=fire_started_on,
            fire_ended_on=fire_ended_on,
            assessed_at=assessed_at,
            assessment=assessment,
            landcover=landcover,
            area_ha=round(area),
            dnbr_mean=round(0.18 + high_share * 0.62, 2),
            geometry=PolygonGeometry(coordinates=[outer]),
            zones=[
                SeverityZone(
                    severity=severity_names[index],
                    area_ha=round(zone_area),
                    geometry=PolygonGeometry(coordinates=[ring]),
                )
                for index, (zone_area, ring) in enumerate(zones)
            ],
            before=ImageryScene(
                satellite="Sentinel-2A",
                product="L2A",
                acquired_on=before_on,
                cloud_cover_pct=rng.randint(0, 12),
                scene_id=f"S2A_MSIL2A_{before_on:%Y%m%d}_{tile}",
            ),
            after=ImageryScene(
                satellite="Sentinel-2B",
                product="L2A",
                acquired_on=after_on,
                cloud_cover_pct=rng.randint(2, 18),
                scene_id=f"S2B_MSIL2A_{after_on:%Y%m%d}_{tile}",
            ),
        )

    def _build_environment(self) -> None:
        rng = random.Random(11)
        showcase = next(
            item for item in catalog.INCIDENTS if item.id == catalog.SHOWCASE_INCIDENT_ID
        )
        for lat in range(50, 72, 2):
            for lon in range(80, 140, 3):
                base_from = (
                    250
                    + 40 * math.sin(math.radians(lon * 4))
                    + 25 * math.cos(math.radians(lat * 9))
                )
                speed = (
                    3 + 3 * (1 + math.sin(math.radians(lon * 3 + lat * 5))) + rng.uniform(0, 1.2)
                )
                for incident in catalog.INCIDENTS:
                    distance = math.hypot(
                        (incident.ignition[0] - lon) * math.cos(math.radians(lat)),
                        incident.ignition[1] - lat,
                    )
                    if distance < 2.2:
                        weight = 1 - distance / 2.2
                        target = (incident.direction_deg + 180) % 360
                        delta = (target - base_from + 540) % 360 - 180
                        base_from += delta * weight
                        speed += (incident.wind_speed_ms - speed) * weight
                self.data.wind.append(
                    WindSample(
                        location=(float(lon), float(lat)),
                        from_deg=round(base_from % 360),
                        speed_ms=round(speed, 1),
                    )
                )
        cloud_specs = (
            (destination(showcase.ignition, 300, 38), 520_000, 72, 0.45, 40),
            ((97.2, 61.4), 1_900_000, 58, 0.3, 10),
            ((92.4, 58.9), 900_000, 35, 0.5, 120),
            ((107.0, 60.2), 1_400_000, 64, 0.35, 70),
            ((118.0, 54.6), 800_000, 41, 0.3, 20),
        )
        for index, (center, area, probability, elongation, axis) in enumerate(cloud_specs):
            ring = blob(center, area, ShapeNoise.seeded(300 + index, 2.2), elongation, axis)
            self.data.clouds.append(
                CloudField(
                    id=f"CL-{index + 1:02d}",
                    probability=probability,
                    geometry=PolygonGeometry(coordinates=[ring]),
                )
            )

    def _build_weekly_stats(self) -> None:
        rng = random.Random(2026)
        season_start = date(2026, 4, 20)
        weights = {"krasnoyarsk": 1.0, "irkutsk": 0.75, "sakha": 0.9, "zabaykalsky": 0.6}
        week = season_start
        week_index = 0
        while week <= self.anchor.date():
            season_curve = math.exp(-(((week_index - 12) / 5.5) ** 2))
            for region_id, weight in weights.items():
                incidents = max(0, round((3 + 38 * season_curve) * weight * rng.uniform(0.7, 1.3)))
                burned = incidents * rng.uniform(220, 680) * (0.6 + season_curve)
                high = burned * rng.uniform(0.18, 0.36)
                confirmation = 150 - week_index * 3.2 + rng.uniform(-12, 12)
                self.data.weekly_stats.append(
                    WeeklyStat(
                        week_start=week,
                        region_id=region_id,
                        incidents=incidents,
                        burned_area_ha=round(burned),
                        high_severity_ha=round(high),
                        mean_confirmation_minutes=round(max(38.0, confirmation), 1),
                    )
                )
            week += timedelta(days=7)
            week_index += 1


def build_dataset(anchor: datetime) -> DemoDataset:
    return DatasetBuilder(anchor).build()
