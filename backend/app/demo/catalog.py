from dataclasses import dataclass
from datetime import date

from app.models.context import Region
from app.models.geometry import Position
from app.models.incident import EvidenceEffect, EvidenceStrength, IncidentStatus

REGIONS: tuple[Region, ...] = (
    Region(
        id="aoi",
        name="Нижнее Поволжье и Подонье",
        short_name="АОИ мониторинга",
        bbox=(38.3, 44.6, 48.0, 52.7),
        center=(43.15, 48.65),
        zoom=5.15,
    ),
    Region(
        id="rostov",
        name="Ростовская область",
        short_name="Ростовская",
        bbox=(38.3, 45.8, 44.2, 50.3),
        center=(41.0, 47.85),
        zoom=6.1,
    ),
    Region(
        id="volgograd",
        name="Волгоградская область",
        short_name="Волгоградская",
        bbox=(41.1, 47.4, 47.5, 51.3),
        center=(44.0, 49.2),
        zoom=6.0,
    ),
    Region(
        id="astrakhan",
        name="Астраханская область",
        short_name="Астраханская",
        bbox=(44.8, 44.8, 48.0, 48.8),
        center=(46.5, 46.6),
        zoom=6.3,
    ),
    Region(
        id="saratov",
        name="Саратовская область (запад и центр)",
        short_name="Саратовская",
        bbox=(42.5, 50.0, 48.0, 52.7),
        center=(45.2, 51.35),
        zoom=6.2,
    ),
    Region(
        id="kalmykia",
        name="Республика Калмыкия",
        short_name="Калмыкия",
        bbox=(44.0, 44.7, 47.6, 48.5),
        center=(45.5, 46.55),
        zoom=6.4,
    ),
    # Демо-сценарий обзора (FIRMS/replay showcase), вне конкурсного AOI
    Region(
        id="krasnoyarsk",
        name="Красноярский край (сценарий)",
        short_name="Красноярский",
        bbox=(78.0, 51.7, 114.0, 77.8),
        center=(95.2, 59.4),
        zoom=4.2,
    ),
    Region(
        id="irkutsk",
        name="Иркутская область (сценарий)",
        short_name="Иркутская",
        bbox=(95.6, 51.1, 119.2, 64.4),
        center=(106.5, 57.8),
        zoom=4.6,
    ),
    Region(
        id="sakha",
        name="Республика Саха (сценарий)",
        short_name="Якутия",
        bbox=(105.5, 55.4, 162.9, 77.2),
        center=(125.0, 63.5),
        zoom=3.6,
    ),
    Region(
        id="zabaykalsky",
        name="Забайкальский край (сценарий)",
        short_name="Забайкальский",
        bbox=(107.7, 49.1, 122.2, 58.4),
        center=(115.5, 53.0),
        zoom=4.9,
    ),
)

REGION_NAMES = {region.id: region.name for region in REGIONS}


@dataclass(frozen=True)
class SatelliteSpec:
    source: str
    instrument: str
    pixel_size_m: int


SATELLITES: dict[str, SatelliteSpec] = {
    "Suomi NPP": SatelliteSpec("VIIRS_SNPP_NRT", "VIIRS", 375),
    "NOAA-20": SatelliteSpec("VIIRS_NOAA20_NRT", "VIIRS", 375),
    "NOAA-21": SatelliteSpec("VIIRS_NOAA21_NRT", "VIIRS", 375),
    "Aqua": SatelliteSpec("MODIS_A_NRT", "MODIS", 1000),
    "Terra": SatelliteSpec("MODIS_T_NRT", "MODIS", 1000),
}


@dataclass(frozen=True)
class SettlementSpec:
    id: str
    name: str
    kind: str
    region_id: str
    location: Position
    population: int


SETTLEMENTS: tuple[SettlementSpec, ...] = (
    SettlementSpec("stl-krasnoyarsk", "Красноярск", "Город", "krasnoyarsk", (92.8932, 56.0153), 1_205_000),
    SettlementSpec("stl-kodinsk", "Кодинск", "Город", "krasnoyarsk", (99.1797, 58.6036), 14_200),
    SettlementSpec("stl-boguchany", "Богучаны", "Село", "krasnoyarsk", (97.4531, 58.3814), 10_700),
    SettlementSpec("stl-motygino", "Мотыгино", "Посёлок", "krasnoyarsk", (94.7667, 58.1833), 5_900),
    SettlementSpec("stl-yeniseysk", "Енисейск", "Город", "krasnoyarsk", (92.1703, 58.4497), 17_300),
    SettlementSpec("stl-lesosibirsk", "Лесосибирск", "Город", "krasnoyarsk", (92.4833, 58.2333), 56_800),
    SettlementSpec("stl-severo-yeniseysky", "Северо-Енисейский", "Посёлок", "krasnoyarsk", (93.0408, 60.3725), 9_800),
    SettlementSpec("stl-baykit", "Байкит", "Село", "krasnoyarsk", (96.3697, 61.6733), 3_100),
    SettlementSpec("stl-vanavara", "Ванавара", "Село", "krasnoyarsk", (102.2797, 60.3397), 2_800),
    SettlementSpec("stl-turukhansk", "Туруханск", "Село", "krasnoyarsk", (87.9611, 65.7956), 4_300),
    SettlementSpec("stl-yartsevo", "Ярцево", "Село", "krasnoyarsk", (89.8667, 60.2500), 2_200),
    SettlementSpec("stl-aban", "Абан", "Посёлок", "krasnoyarsk", (96.0636, 56.6769), 8_700),
    SettlementSpec("stl-kansk", "Канск", "Город", "krasnoyarsk", (95.7050, 56.2050), 88_000),
    SettlementSpec("stl-dolgy-most", "Долгий Мост", "Село", "krasnoyarsk", (96.8406, 56.7406), 4_100),
    SettlementSpec("stl-erbogachen", "Ербогачён", "Село", "irkutsk", (108.0100, 61.2750), 2_600),
    SettlementSpec("stl-ust-kut", "Усть-Кут", "Город", "irkutsk", (105.7581, 56.7936), 38_900),
    SettlementSpec("stl-lensk", "Ленск", "Город", "sakha", (114.9278, 60.7253), 22_600),
    SettlementSpec("stl-mogocha", "Могоча", "Город", "zabaykalsky", (119.7667, 53.7333), 11_700),
    SettlementSpec("stl-ksenyevka", "Ксеньевка", "Посёлок", "zabaykalsky", (118.7333, 53.5667), 2_400),
)


@dataclass(frozen=True)
class LinearSpec:
    id: str
    kind: str
    name: str
    subtitle: str
    region_id: str
    coordinates: tuple[Position, ...]


LINEAR_OBJECTS: tuple[LinearSpec, ...] = (
    LinearSpec(
        "pl-kodinsk-220",
        "power_line",
        "ЛЭП 220 кВ",
        "Богучанская ГЭС — Кодинск",
        "krasnoyarsk",
        ((99.105, 58.705), (99.300, 58.600), (99.520, 58.542), (99.760, 58.522), (100.050, 58.500)),
    ),
    LinearSpec(
        "rd-kodinsk-boguchany",
        "road",
        "Автодорога Кодинск — Богучаны",
        "Региональная дорога",
        "krasnoyarsk",
        ((99.180, 58.600), (99.290, 58.520), (99.345, 58.430), (99.260, 58.330), (98.900, 58.250), (98.300, 58.300), (97.453, 58.381)),
    ),
    LinearSpec(
        "pl-boguchany-110",
        "power_line",
        "ЛЭП 110 кВ",
        "Богучаны — Таёжный",
        "krasnoyarsk",
        ((97.453, 58.381), (97.700, 58.300), (97.950, 58.180), (98.150, 58.080)),
    ),
    LinearSpec(
        "rd-kansk-aban",
        "road",
        "Автодорога Канск — Абан — Богучаны",
        "Региональная дорога",
        "krasnoyarsk",
        ((95.705, 56.205), (95.900, 56.450), (96.064, 56.677), (96.300, 56.900), (96.600, 57.250)),
    ),
    LinearSpec(
        "rw-transsib-mogocha",
        "road",
        "Транссибирская магистраль",
        "Железная дорога",
        "zabaykalsky",
        ((118.300, 53.500), (118.733, 53.567), (119.100, 53.690), (119.767, 53.733), (120.300, 53.820)),
    ),
)


@dataclass(frozen=True)
class PointObjectSpec:
    id: str
    name: str
    subtitle: str
    region_id: str
    location: Position


INFRASTRUCTURE: tuple[PointObjectSpec, ...] = (
    PointObjectSpec("inf-kodinsk-substation", "Подстанция 220 кВ", "Энергообъект", "krasnoyarsk", (99.300, 58.600)),
    PointObjectSpec("inf-boguchany-hpp", "Богучанская ГЭС", "Энергообъект", "krasnoyarsk", (99.080, 58.710)),
    PointObjectSpec("inf-kezhma-timber", "Лесозаготовительный участок", "Производственный объект", "krasnoyarsk", (99.740, 58.520)),
    PointObjectSpec("inf-aban-depot", "Склад ГСМ", "Опасный объект", "krasnoyarsk", (96.180, 56.760)),
    PointObjectSpec("inf-mogocha-station", "Станция Могоча", "Железнодорожная станция", "zabaykalsky", (119.760, 53.740)),
)


@dataclass(frozen=True)
class AreaSpec:
    id: str
    name: str
    subtitle: str
    region_id: str
    center: Position
    area_ha: float
    elongation: float
    axis_deg: float
    seed: int


PROTECTED_AREAS: tuple[AreaSpec, ...] = (
    AreaSpec("pa-tsentralnosibirsky", "Центральносибирский заповедник", "ООПТ федерального значения", "krasnoyarsk", (90.20, 61.55), 972_000, 0.35, 20, 71),
    AreaSpec("pa-tungussky", "Тунгусский заповедник", "ООПТ федерального значения", "krasnoyarsk", (101.30, 60.90), 296_000, 0.25, 70, 72),
    AreaSpec("pa-stolby", "Красноярские Столбы", "Национальный парк", "krasnoyarsk", (92.78, 55.93), 47_000, 0.2, 110, 73),
)


@dataclass(frozen=True)
class ThermalSourceSpec:
    id: str
    name: str
    kind: str
    location: Position
    observation_count: int
    history_years: float
    mean_frp_mw: float
    daily_detections: int


THERMAL_SOURCES: tuple[ThermalSourceSpec, ...] = (
    ThermalSourceSpec("ts-vankor", "Ванкорское месторождение, факел", "gas_flare", (83.55, 67.80), 1_184, 6.8, 48.0, 3),
    ThermalSourceSpec("ts-kuyumba", "Куюмбинское месторождение, факел", "gas_flare", (97.32, 60.94), 142, 2.4, 21.0, 2),
    ThermalSourceSpec("ts-achinsk", "Ачинский глинозёмный комбинат", "industrial", (90.43, 56.27), 516, 5.1, 16.0, 1),
    ThermalSourceSpec("ts-norilsk", "Надеждинский металлургический завод", "industrial", (87.99, 69.32), 877, 6.2, 34.0, 2),
    ThermalSourceSpec("ts-verkhnechonsk", "Верхнечонское месторождение, факел", "gas_flare", (106.10, 60.80), 403, 3.9, 27.0, 2),
    ThermalSourceSpec("ts-talakan", "Талаканское месторождение, факел", "gas_flare", (111.10, 59.90), 611, 4.6, 31.0, 2),
)


@dataclass(frozen=True)
class StageSpec:
    hours_ago: float
    satellite: str
    status: IncidentStatus
    confidence: int
    threat: int
    priority: int
    area_ha: float
    frp_mw: float
    pixels: int


@dataclass(frozen=True)
class EvidenceSpec:
    code: str
    label: str
    detail: str
    effect: EvidenceEffect
    strength: EvidenceStrength


@dataclass(frozen=True)
class IncidentSpec:
    id: str
    region_id: str
    district: str
    ignition: Position
    direction_deg: float
    eccentricity: float
    landcover: str
    wind_speed_ms: float
    spread_speed_m_per_h: float
    updated_minutes_ago: int
    seed: int
    stages: tuple[StageSpec, ...]
    evidence: tuple[EvidenceSpec, ...]
    burn_scar_id: str | None = None


SHOWCASE_INCIDENT_ID = "KR-042"

INCIDENTS: tuple[IncidentSpec, ...] = (
    IncidentSpec(
        id="KR-042",
        region_id="krasnoyarsk",
        district="Кежемский район",
        ignition=(99.4756, 58.4687),
        direction_deg=311,
        eccentricity=0.62,
        landcover="Тёмнохвойная тайга",
        wind_speed_ms=7.2,
        spread_speed_m_per_h=310,
        updated_minutes_ago=4,
        seed=42,
        burn_scar_id="BS-2026-116",
        stages=(
            StageSpec(19.2, "NOAA-20", "suspected", 41, 34, 38, 35, 18, 2),
            StageSpec(17.4, "Terra", "suspected", 58, 41, 45, 90, 42, 2),
            StageSpec(15.7, "Suomi NPP", "confirmed", 79, 52, 58, 210, 64, 6),
            StageSpec(12.0, "NOAA-21", "confirmed", 88, 61, 66, 420, 132, 11),
            StageSpec(9.1, "Aqua", "confirmed", 90, 70, 74, 690, 176, 7),
            StageSpec(6.8, "NOAA-20", "confirmed", 93, 79, 83, 1050, 241, 23),
            StageSpec(3.3, "Suomi NPP", "confirmed", 95, 85, 88, 1480, 305, 31),
            StageSpec(0.87, "NOAA-21", "confirmed", 96, 88, 91, 1860, 356, 38),
        ),
        evidence=(
            EvidenceSpec("repeat_observation", "Повторное спутниковое наблюдение", "8 пролётов за 18 ч: NOAA-20, NOAA-21, Suomi NPP, Aqua, Terra", "raises", "strong"),
            EvidenceSpec("frp_growth", "Рост FRP", "18 → 356 МВт за 18 ч", "raises", "strong"),
            EvidenceSpec("forest_cover", "Лесная территория", "Тёмнохвойная тайга, 94% покрытия в радиусе 5 км", "raises", "moderate"),
            EvidenceSpec("wind_toward_settlement", "Ветер в сторону населённого пункта", "ЮВ 7 м/с, кромка смещается к Кодинску, автодорога в зоне P95", "raises", "strong"),
            EvidenceSpec("no_persistent_source", "Нет постоянного теплового источника", "Thermal Memory: 0 аномалий за 3 года в радиусе 2 км", "raises", "moderate"),
            EvidenceSpec("optical_cloud", "Облачность на оптическом пролёте", "Sentinel-2B: вероятность облаков 72%, уточнение площади отложено", "lowers", "weak"),
        ),
    ),
    IncidentSpec(
        id="KR-045",
        region_id="zabaykalsky",
        district="Могочинский район",
        ignition=(119.22, 53.60),
        direction_deg=62,
        eccentricity=0.55,
        landcover="Лиственничная тайга",
        wind_speed_ms=9.4,
        spread_speed_m_per_h=420,
        updated_minutes_ago=11,
        seed=45,
        stages=(
            StageSpec(11.3, "Aqua", "suspected", 52, 48, 51, 140, 55, 2),
            StageSpec(8.6, "NOAA-21", "confirmed", 81, 66, 70, 520, 148, 9),
            StageSpec(5.2, "Suomi NPP", "confirmed", 90, 80, 81, 980, 212, 15),
            StageSpec(1.9, "NOAA-20", "confirmed", 92, 86, 86, 1320, 268, 21),
        ),
        evidence=(
            EvidenceSpec("repeat_observation", "Повторное спутниковое наблюдение", "4 пролёта за 10 ч", "raises", "strong"),
            EvidenceSpec("near_railway", "Близость к Транссибу", "Кромка в 8,2 км от железной дороги", "raises", "strong"),
            EvidenceSpec("wind_speed", "Сильный ветер", "ЮЗ 9 м/с, порывы до 14 м/с", "raises", "moderate"),
            EvidenceSpec("no_persistent_source", "Нет постоянного теплового источника", "Thermal Memory: аномалий не зафиксировано", "raises", "moderate"),
        ),
    ),
    IncidentSpec(
        id="KR-040",
        region_id="krasnoyarsk",
        district="Абанский район",
        ignition=(96.46, 56.83),
        direction_deg=248,
        eccentricity=0.5,
        landcover="Смешанный лес, вырубки",
        wind_speed_ms=5.1,
        spread_speed_m_per_h=180,
        updated_minutes_ago=23,
        seed=40,
        stages=(
            StageSpec(40.0, "Suomi NPP", "suspected", 47, 51, 50, 45, 21, 2),
            StageSpec(31.5, "NOAA-20", "confirmed", 76, 66, 68, 160, 58, 5),
            StageSpec(22.0, "Aqua", "confirmed", 84, 74, 76, 310, 81, 4),
            StageSpec(13.4, "NOAA-21", "confirmed", 88, 81, 82, 470, 110, 10),
            StageSpec(4.6, "Suomi NPP", "confirmed", 90, 84, 85, 560, 96, 9),
        ),
        evidence=(
            EvidenceSpec("near_settlement", "Близость населённого пункта", "Долгий Мост — 24 км, Абан — 27 км", "raises", "strong"),
            EvidenceSpec("hazardous_object", "Опасный объект рядом", "Склад ГСМ в 16 км от кромки", "raises", "strong"),
            EvidenceSpec("repeat_observation", "Повторное спутниковое наблюдение", "5 пролётов за 36 ч", "raises", "moderate"),
            EvidenceSpec("frp_decline", "Снижение FRP", "110 → 96 МВт на последнем пролёте", "lowers", "weak"),
        ),
    ),
    IncidentSpec(
        id="KR-038",
        region_id="krasnoyarsk",
        district="Богучанский район",
        ignition=(97.86, 58.24),
        direction_deg=96,
        eccentricity=0.58,
        landcover="Сосновые леса",
        wind_speed_ms=6.0,
        spread_speed_m_per_h=240,
        updated_minutes_ago=17,
        seed=38,
        stages=(
            StageSpec(52.0, "Terra", "suspected", 44, 38, 40, 60, 24, 1),
            StageSpec(44.8, "NOAA-21", "confirmed", 74, 52, 57, 240, 71, 6),
            StageSpec(33.1, "Suomi NPP", "confirmed", 86, 63, 67, 780, 154, 14),
            StageSpec(20.5, "NOAA-20", "confirmed", 91, 71, 74, 1420, 202, 18),
            StageSpec(8.2, "Aqua", "confirmed", 93, 75, 78, 2110, 188, 9),
        ),
        evidence=(
            EvidenceSpec("repeat_observation", "Повторное спутниковое наблюдение", "5 пролётов за 44 ч", "raises", "strong"),
            EvidenceSpec("infrastructure", "ЛЭП пересекает периметр", "ЛЭП 110 кВ Богучаны — Таёжный, зона P50", "raises", "moderate"),
            EvidenceSpec("forest_cover", "Лесная территория", "Сосновые леса, высокая горимость", "raises", "moderate"),
            EvidenceSpec("wind_away", "Ветер от населённого пункта", "З 6 м/с, Богучаны вне прогнозного коридора", "lowers", "moderate"),
        ),
    ),
    IncidentSpec(
        id="KR-037",
        region_id="irkutsk",
        district="Катангский район",
        ignition=(107.42, 61.08),
        direction_deg=35,
        eccentricity=0.6,
        landcover="Лиственничная тайга",
        wind_speed_ms=6.8,
        spread_speed_m_per_h=260,
        updated_minutes_ago=34,
        seed=37,
        stages=(
            StageSpec(70.0, "Aqua", "suspected", 49, 30, 36, 120, 40, 2),
            StageSpec(55.0, "NOAA-20", "confirmed", 83, 44, 52, 860, 170, 16),
            StageSpec(38.5, "Suomi NPP", "confirmed", 91, 57, 62, 2300, 260, 27),
            StageSpec(21.0, "NOAA-21", "confirmed", 94, 64, 68, 3900, 310, 30),
            StageSpec(6.1, "Terra", "confirmed", 95, 66, 69, 4700, 240, 12),
        ),
        evidence=(
            EvidenceSpec("large_area", "Крупная площадь", "Оценка 4 700 га, рост 21% за сутки", "raises", "strong"),
            EvidenceSpec("repeat_observation", "Повторное спутниковое наблюдение", "5 пролётов за 64 ч", "raises", "strong"),
            EvidenceSpec("remote_area", "Удалённость от населённых пунктов", "Ербогачён — 32 км", "lowers", "moderate"),
        ),
    ),
    IncidentSpec(
        id="KR-044",
        region_id="krasnoyarsk",
        district="Мотыгинский район",
        ignition=(95.18, 58.06),
        direction_deg=40,
        eccentricity=0.45,
        landcover="Смешанный лес",
        wind_speed_ms=4.2,
        spread_speed_m_per_h=120,
        updated_minutes_ago=9,
        seed=44,
        stages=(
            StageSpec(3.4, "Suomi NPP", "suspected", 55, 58, 57, 40, 26, 3),
            StageSpec(1.1, "NOAA-21", "suspected", 68, 61, 63, 75, 44, 4),
        ),
        evidence=(
            EvidenceSpec("repeat_observation", "Два наблюдения подряд", "Suomi NPP и NOAA-21 с интервалом 2,3 ч", "raises", "moderate"),
            EvidenceSpec("near_settlement", "Близость населённого пункта", "Мотыгино — 27 км", "raises", "moderate"),
            EvidenceSpec("awaiting_confirmation", "Ожидает подтверждения", "Нужен третий пролёт или оптический снимок", "lowers", "moderate"),
        ),
    ),
    IncidentSpec(
        id="KR-035",
        region_id="krasnoyarsk",
        district="Эвенкийский район",
        ignition=(97.05, 61.98),
        direction_deg=18,
        eccentricity=0.52,
        landcover="Лиственничная тайга",
        wind_speed_ms=3.8,
        spread_speed_m_per_h=90,
        updated_minutes_ago=48,
        seed=35,
        stages=(
            StageSpec(150.0, "Terra", "suspected", 45, 28, 30, 300, 60, 3),
            StageSpec(128.0, "NOAA-20", "confirmed", 86, 40, 45, 2400, 290, 35),
            StageSpec(96.0, "Suomi NPP", "confirmed", 92, 47, 53, 4900, 330, 38),
            StageSpec(60.0, "NOAA-21", "confirmed", 93, 50, 56, 6100, 210, 24),
            StageSpec(26.0, "Aqua", "monitoring", 90, 46, 54, 6400, 120, 8),
        ),
        evidence=(
            EvidenceSpec("large_area", "Крупная площадь", "6 400 га, рост замедлился", "raises", "moderate"),
            EvidenceSpec("control_zone", "Зона контроля", "Тушение не ведётся, мониторинг по спутникам", "lowers", "strong"),
            EvidenceSpec("frp_decline", "Снижение FRP", "330 → 120 МВт за 70 ч", "lowers", "moderate"),
        ),
    ),
    IncidentSpec(
        id="KR-046",
        region_id="krasnoyarsk",
        district="Енисейский район",
        ignition=(90.62, 60.08),
        direction_deg=75,
        eccentricity=0.4,
        landcover="Заболоченная тайга",
        wind_speed_ms=3.1,
        spread_speed_m_per_h=60,
        updated_minutes_ago=14,
        seed=46,
        stages=(
            StageSpec(1.6, "NOAA-20", "suspected", 46, 36, 47, 20, 12, 2),
        ),
        evidence=(
            EvidenceSpec("single_observation", "Одно наблюдение", "NOAA-20 VIIRS, 2 пикселя", "lowers", "strong"),
            EvidenceSpec("no_persistent_source", "Нет постоянного теплового источника", "Thermal Memory: аномалий не зафиксировано", "raises", "moderate"),
            EvidenceSpec("near_settlement", "Близость населённого пункта", "Ярцево — 45 км", "raises", "weak"),
        ),
    ),
    IncidentSpec(
        id="KR-033",
        region_id="sakha",
        district="Ленский район",
        ignition=(113.95, 60.32),
        direction_deg=300,
        eccentricity=0.5,
        landcover="Лиственничная тайга",
        wind_speed_ms=4.5,
        spread_speed_m_per_h=110,
        updated_minutes_ago=52,
        seed=33,
        stages=(
            StageSpec(96.0, "Aqua", "suspected", 50, 30, 34, 180, 50, 2),
            StageSpec(74.0, "NOAA-21", "confirmed", 84, 40, 44, 1300, 180, 17),
            StageSpec(40.0, "Suomi NPP", "confirmed", 89, 44, 47, 2500, 160, 19),
            StageSpec(10.0, "NOAA-20", "monitoring", 88, 42, 44, 2800, 90, 7),
        ),
        evidence=(
            EvidenceSpec("control_zone", "Зона контроля", "Мониторинг, наземные силы не задействованы", "lowers", "strong"),
            EvidenceSpec("frp_decline", "Снижение FRP", "180 → 90 МВт", "lowers", "moderate"),
            EvidenceSpec("near_settlement", "Населённый пункт", "Ленск — 67 км", "raises", "weak"),
        ),
    ),
    IncidentSpec(
        id="KR-031",
        region_id="krasnoyarsk",
        district="Северо-Енисейский район",
        ignition=(93.62, 60.71),
        direction_deg=130,
        eccentricity=0.45,
        landcover="Тёмнохвойная тайга",
        wind_speed_ms=2.6,
        spread_speed_m_per_h=40,
        updated_minutes_ago=66,
        seed=31,
        stages=(
            StageSpec(110.0, "Terra", "suspected", 48, 26, 28, 90, 30, 2),
            StageSpec(86.0, "NOAA-20", "confirmed", 80, 33, 36, 420, 88, 9),
            StageSpec(50.0, "NOAA-21", "confirmed", 85, 31, 34, 610, 52, 6),
            StageSpec(18.0, "Suomi NPP", "monitoring", 82, 29, 32, 640, 24, 3),
        ),
        evidence=(
            EvidenceSpec("frp_decline", "Низкая интенсивность", "FRP 24 МВт, 3 пикселя", "lowers", "strong"),
            EvidenceSpec("remote_area", "Удалённость", "Северо-Енисейский — 48 км", "lowers", "moderate"),
        ),
    ),
    IncidentSpec(
        id="KR-029",
        region_id="krasnoyarsk",
        district="Туруханский район",
        ignition=(88.55, 65.42),
        direction_deg=210,
        eccentricity=0.4,
        landcover="Северная тайга",
        wind_speed_ms=3.0,
        spread_speed_m_per_h=20,
        updated_minutes_ago=95,
        seed=29,
        stages=(
            StageSpec(160.0, "Aqua", "suspected", 52, 22, 25, 150, 40, 2),
            StageSpec(132.0, "NOAA-21", "confirmed", 83, 26, 29, 980, 120, 12),
            StageSpec(84.0, "Suomi NPP", "confirmed", 87, 22, 24, 1250, 60, 7),
            StageSpec(30.0, "NOAA-20", "localized", 80, 14, 21, 1290, 9, 1),
        ),
        evidence=(
            EvidenceSpec("localized", "Локализован", "Рост площади остановлен 54 ч назад", "lowers", "strong"),
            EvidenceSpec("frp_decline", "Затухание", "FRP 9 МВт, 1 пиксель", "lowers", "strong"),
        ),
    ),
)


@dataclass(frozen=True)
class ForecastSpec:
    level: str
    area_multiplier: float
    eccentricity_delta: float


FORECAST_LEVELS: tuple[ForecastSpec, ...] = (
    ForecastSpec("p50", 2.6, 0.1),
    ForecastSpec("p80", 4.6, 0.1),
    ForecastSpec("p95", 7.2, 0.08),
)


@dataclass(frozen=True)
class BurnScarSpec:
    id: str
    name: str
    region_id: str
    district: str
    center: Position
    low_ha: float
    moderate_ha: float
    high_ha: float
    fire_started_on: date
    fire_ended_on: date
    before_on: date
    after_on: date
    landcover: str
    elongation: float
    axis_deg: float
    seed: int


BURN_SCARS: tuple[BurnScarSpec, ...] = (
    BurnScarSpec("BS-2026-087", "Гарь у Тэтэрэ", "krasnoyarsk", "Эвенкийский район", (98.32, 61.41), 5210, 8640, 4570, date(2026, 7, 3), date(2026, 7, 29), date(2026, 6, 27), date(2026, 8, 4), "Лиственничная тайга", 0.45, 30, 87),
    BurnScarSpec("BS-2026-103", "Гарь Нижняя Тунгуска", "irkutsk", "Катангский район", (106.52, 61.62), 3120, 4410, 2320, date(2026, 7, 21), date(2026, 8, 12), date(2026, 7, 14), date(2026, 8, 17), "Лиственничная тайга", 0.3, 65, 103),
    BurnScarSpec("BS-2026-079", "Гарь у Витима", "sakha", "Ленский район", (114.62, 60.93), 1880, 2140, 1100, date(2026, 6, 30), date(2026, 7, 16), date(2026, 6, 22), date(2026, 7, 23), "Лиственничная тайга", 0.25, 120, 79),
    BurnScarSpec("BS-2026-071", "Гарь Кова", "krasnoyarsk", "Кежемский район", (100.25, 58.86), 1040, 1470, 750, date(2026, 6, 24), date(2026, 7, 8), date(2026, 6, 19), date(2026, 7, 12), "Тёмнохвойная тайга", 0.4, 100, 71),
    BurnScarSpec("BS-2026-099", "Гарь Вангаш", "krasnoyarsk", "Северо-Енисейский район", (92.84, 60.96), 1120, 1210, 575, date(2026, 8, 2), date(2026, 8, 19), date(2026, 7, 28), date(2026, 8, 24), "Тёмнохвойная тайга", 0.35, 45, 99),
    BurnScarSpec("BS-2026-110", "Гарь у Ксеньевки", "zabaykalsky", "Могочинский район", (118.95, 53.40), 820, 960, 460, date(2026, 8, 20), date(2026, 8, 30), date(2026, 8, 14), date(2026, 9, 3), "Лиственничная тайга", 0.3, 160, 110),
    BurnScarSpec("BS-2026-092", "Гарь Рыбное", "krasnoyarsk", "Мотыгинский район", (94.52, 58.44), 510, 640, 320, date(2026, 7, 25), date(2026, 8, 3), date(2026, 7, 19), date(2026, 8, 8), "Смешанный лес", 0.3, 20, 92),
    BurnScarSpec("BS-2026-064", "Гарь Ангарская", "krasnoyarsk", "Богучанский район", (97.96, 58.55), 122, 391, 301, date(2026, 6, 18), date(2026, 6, 24), date(2026, 6, 14), date(2026, 6, 29), "Сосновые леса", 0.5, 75, 64),
    BurnScarSpec("BS-2026-058", "Гарь Кемь", "krasnoyarsk", "Енисейский район", (91.02, 59.12), 260, 250, 130, date(2026, 6, 9), date(2026, 6, 15), date(2026, 6, 3), date(2026, 6, 19), "Заболоченная тайга", 0.2, 10, 58),
)


@dataclass(frozen=True)
class DetectionClusterSpec:
    region_id: str | None
    center: Position
    radius_km: float
    count: int
    high_share: float
    seed: int


BACKGROUND_DETECTIONS: tuple[DetectionClusterSpec, ...] = (
    DetectionClusterSpec("krasnoyarsk", (95.70, 56.35), 70, 120, 0.1, 101),
    DetectionClusterSpec("krasnoyarsk", (90.60, 56.20), 55, 90, 0.08, 102),
    DetectionClusterSpec("krasnoyarsk", (91.80, 53.80), 75, 140, 0.12, 103),
    DetectionClusterSpec("irkutsk", (103.80, 53.30), 90, 160, 0.1, 104),
    DetectionClusterSpec(None, (107.60, 51.60), 120, 180, 0.12, 105),
    DetectionClusterSpec("zabaykalsky", (115.40, 51.40), 150, 260, 0.15, 106),
    DetectionClusterSpec(None, (128.20, 50.60), 150, 300, 0.18, 107),
    DetectionClusterSpec("sakha", (129.70, 62.10), 120, 80, 0.2, 108),
    DetectionClusterSpec(None, (84.90, 56.80), 90, 60, 0.1, 109),
    DetectionClusterSpec(None, (82.90, 54.20), 110, 120, 0.08, 110),
    DetectionClusterSpec(None, (135.10, 49.40), 120, 140, 0.14, 111),
    DetectionClusterSpec("krasnoyarsk", (99.80, 58.20), 90, 14, 0.05, 112),
    DetectionClusterSpec("krasnoyarsk", (94.00, 60.50), 300, 60, 0.03, 113),
    DetectionClusterSpec(None, (112.00, 59.50), 400, 70, 0.03, 114),
)
