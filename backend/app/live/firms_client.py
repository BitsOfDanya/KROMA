import csv
import hashlib
import io
from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.live.models import LiveDetection

VIIRS_SATELLITE_LABELS = {
    "N": "Suomi NPP",
    "N20": "NOAA-20",
    "N21": "NOAA-21",
    "1": "NOAA-20",
}


class FirmsError(RuntimeError):
    pass


def _instrument_for(source: str) -> tuple[str, int]:
    if source.startswith("VIIRS"):
        return "VIIRS", 375
    return "MODIS", 1000


def _confidence_bucket(raw: str, instrument: str) -> str:
    value = raw.strip().lower()
    if instrument == "VIIRS":
        return value if value in ("l", "n", "h") else "n"
    try:
        numeric = float(value)
    except ValueError:
        return "n"
    if numeric >= 80:
        return "h"
    if numeric >= 30:
        return "n"
    return "l"


def _satellite_label(source: str, raw: str) -> str:
    if source.startswith("VIIRS"):
        return VIIRS_SATELLITE_LABELS.get(raw.strip(), raw.strip() or source)
    return raw.strip() or source


def parse_csv(text: str, source: str) -> list[LiveDetection]:
    instrument, pixel_size_m = _instrument_for(source)
    reader = csv.DictReader(io.StringIO(text))
    detections: list[LiveDetection] = []
    for row in reader:
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
            acquired_at = datetime.strptime(
                f"{row['acq_date']} {row['acq_time'].zfill(4)}", "%Y-%m-%d %H%M"
            ).replace(tzinfo=UTC)
            brightness_raw = row.get("bright_ti4") or row.get("brightness")
            brightness_k = float(brightness_raw) if brightness_raw else 0.0
            frp_raw = row.get("frp")
            frp_mw = float(frp_raw) if frp_raw not in (None, "") else None
            daynight = (row.get("daynight") or "D").strip().upper()
            daynight = daynight if daynight in ("D", "N") else "D"
        except (KeyError, ValueError):
            continue
        satellite = _satellite_label(source, row.get("satellite", ""))
        identity = f"{source}|{satellite}|{acquired_at.isoformat()}|{latitude:.5f}|{longitude:.5f}"
        detections.append(
            LiveDetection(
                id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                source=source,
                satellite=satellite,
                instrument=instrument,
                acquired_at=acquired_at,
                location=(round(longitude, 5), round(latitude, 5)),
                frp_mw=frp_mw,
                brightness_k=brightness_k,
                source_confidence=_confidence_bucket(row.get("confidence", ""), instrument),
                daynight=daynight,
                pixel_size_m=pixel_size_m,
            )
        )
    return detections


async def fetch_source(
    client: httpx.AsyncClient, settings: Settings, source: str
) -> list[LiveDetection]:
    if not settings.firms_api_key:
        raise FirmsError("NASA_FIRMS_API_KEY is not configured")
    url = "/".join(
        (
            settings.firms_base_url.rstrip("/"),
            settings.firms_api_key,
            source,
            settings.live_area,
            str(settings.live_day_range),
        )
    )
    response = await client.get(url, timeout=30.0)
    response.raise_for_status()
    body = response.text
    if body.lstrip().lower().startswith(("<html", "invalid", "error")):
        raise FirmsError(f"FIRMS rejected request for {source}: {body[:200]}")
    return parse_csv(body, source)


async def fetch_all(settings: Settings) -> list[LiveDetection]:
    detections: list[LiveDetection] = []
    async with httpx.AsyncClient() as client:
        for source in settings.live_sources:
            detections.extend(await fetch_source(client, settings, source))
    return detections
