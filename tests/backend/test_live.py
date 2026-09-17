from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.live.clustering import cluster_detections
from app.live.firms_client import parse_csv
from app.live.models import LiveDetection
from app.live.store import LiveStore

VIIRS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
58.60000,99.18000,335.2,0.4,0.4,2026-09-17,0413,N,VIIRS,h,2.0,310.5,64.2,D
58.60300,99.18200,331.0,0.4,0.4,2026-09-17,0413,N,VIIRS,n,2.0,300.1,41.0,D
-8.97608,17.03142,320.1,0.5,0.5,2026-09-17,0600,N20,VIIRS,l,2.0,295.0,12.0,N
"""


def test_parse_csv_normalizes_viirs_rows() -> None:
    detections = parse_csv(VIIRS_CSV, "VIIRS_SNPP_NRT")

    assert len(detections) == 3
    first = detections[0]
    assert first.instrument == "VIIRS"
    assert first.satellite == "Suomi NPP"
    assert first.source_confidence == "h"
    assert first.pixel_size_m == 375
    assert first.location == (99.18, 58.6)
    assert first.acquired_at == datetime(2026, 9, 17, 4, 13, tzinfo=UTC)


def test_parse_csv_skips_malformed_rows() -> None:
    broken = "latitude,longitude,acq_date,acq_time\nnot-a-number,10,2026-09-17,0100\n"
    assert parse_csv(broken, "VIIRS_SNPP_NRT") == []


def test_cluster_detections_groups_nearby_points_and_bucketizes_far_ones() -> None:
    detections = parse_csv(VIIRS_CSV, "VIIRS_SNPP_NRT")

    incidents = cluster_detections(detections, radius_km=6, window_hours=48)

    assert len(incidents) == 2
    grouped = max(incidents, key=lambda item: item.detection_count)
    assert grouped.detection_count == 2
    assert grouped.status == "confirmed"
    assert grouped.frp_mw > 0
    lone = min(incidents, key=lambda item: item.detection_count)
    assert lone.detection_count == 1
    assert lone.status == "suspected"


def test_cluster_marks_old_confirmed_clusters_as_monitoring() -> None:
    base = datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
    old = [
        LiveDetection(
            id="a",
            source="VIIRS_SNPP_NRT",
            satellite="Suomi NPP",
            instrument="VIIRS",
            acquired_at=base,
            location=(99.0, 58.0),
            frp_mw=50,
            brightness_k=330,
            source_confidence="h",
            daynight="D",
            pixel_size_m=375,
        ),
        LiveDetection(
            id="b",
            source="VIIRS_SNPP_NRT",
            satellite="Suomi NPP",
            instrument="VIIRS",
            acquired_at=base + timedelta(minutes=5),
            location=(99.001, 58.001),
            frp_mw=40,
            brightness_k=330,
            source_confidence="h",
            daynight="D",
            pixel_size_m=375,
        ),
        LiveDetection(
            id="c",
            source="VIIRS_SNPP_NRT",
            satellite="Suomi NPP",
            instrument="VIIRS",
            acquired_at=base + timedelta(hours=30),
            location=(10.0, 10.0),
            frp_mw=5,
            brightness_k=320,
            source_confidence="l",
            daynight="D",
            pixel_size_m=375,
        ),
    ]

    incidents = cluster_detections(old, radius_km=6, window_hours=48)

    stale = next(item for item in incidents if item.detection_count == 2)
    assert stale.status == "monitoring"


def test_live_store_status_without_api_key_is_offline() -> None:
    store = LiveStore(Settings(firms_api_key=None))

    status = store.status()

    assert status.configured is False
    assert status.status == "offline"
    assert status.error is not None


def test_live_store_status_reflects_freshness_after_refresh() -> None:
    settings = Settings(firms_api_key="test-key", live_refresh_seconds=600)
    store = LiveStore(settings)
    store._state.last_success_at = datetime.now(UTC)
    store._state.last_fetch_at = store._state.last_success_at

    assert store.status().status == "live"

    store._state.last_success_at = datetime.now(UTC) - timedelta(seconds=1800)
    assert store.status().status == "nrt"

    store._state.last_success_at = datetime.now(UTC) - timedelta(hours=6)
    assert store.status().status == "stale"
