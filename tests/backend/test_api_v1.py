from datetime import timedelta

from conftest import ANCHOR


def test_overview_counts_active_incidents(api) -> None:
    body = api("/api/v1/overview").json()

    assert body["data_source"] == "demo"
    assert body["counts"]["active"] == 10
    assert body["counts"]["critical"] == 3
    assert body["top_incident_id"] == "KR-042"
    assert {region["id"] for region in body["regions"]} >= {"krasnoyarsk", "irkutsk"}


def test_incident_list_is_sorted_by_priority(api) -> None:
    response = api("/api/v1/incidents")
    body = response.json()
    priorities = [item["priority"] for item in body["items"]]

    assert response.status_code == 200
    assert body["total"] == len(body["items"]) == 11
    assert priorities == sorted(priorities, reverse=True)
    assert body["items"][0]["id"] == "KR-042"


def test_incident_list_filters(api) -> None:
    body = api("/api/v1/incidents?status=confirmed&priority_min=70&region=krasnoyarsk").json()

    assert body["items"]
    assert all(item["status"] == "confirmed" for item in body["items"])
    assert all(item["priority"] >= 70 for item in body["items"])
    assert all(item["region_id"] == "krasnoyarsk" for item in body["items"])


def test_incident_list_filters_by_bbox_and_time(api) -> None:
    body = api("/api/v1/incidents?bbox=98,57,101,60").json()
    assert [item["id"] for item in body["items"]] == ["KR-042"]

    since = (ANCHOR - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    recent = api(f"/api/v1/incidents?from={since}").json()
    assert all(item["updated_at"] >= since for item in recent["items"])


def test_incident_list_rejects_invalid_parameters(api) -> None:
    assert api("/api/v1/incidents?bbox=1,2,3").status_code == 422
    assert api("/api/v1/incidents?status=burning").status_code == 422
    assert api("/api/v1/incidents?priority_min=140").status_code == 422


def test_incident_detail(api) -> None:
    body = api("/api/v1/incidents/KR-042").json()

    assert (body["confidence"], body["threat"], body["priority"]) == (96, 88, 91)
    assert body["severity"] == "critical"
    assert body["nearest_settlement"]["name"] == "Кодинск"
    assert body["evidence"]
    assert body["exposures"][0]["distance_km"] <= body["exposures"][-1]["distance_km"]
    assert all(item["overpass_at"] > body["updated_at"] for item in body["next_passes"])
    assert [zone["level"] for zone in body["forecast"]] == ["p50", "p80", "p95"]


def test_unknown_incident_returns_404(api) -> None:
    response = api("/api/v1/incidents/KR-999")

    assert response.status_code == 404


def test_incident_timeline_and_observations(api) -> None:
    timeline = api("/api/v1/incidents/KR-042/timeline").json()
    observations = api("/api/v1/incidents/KR-042/observations").json()

    assert len(timeline["snapshots"]) == 8
    assert timeline["events"][0]["kind"] == "detected"
    assert observations["type"] == "FeatureCollection"
    assert observations["meta"]["count"] == timeline["snapshots"][-1]["observation_count"]


def test_forecast_is_geojson_polygons(api) -> None:
    body = api("/api/v1/incidents/KR-042/forecast").json()

    assert {feature["properties"]["level"] for feature in body["features"]} == {"p50", "p80", "p95"}
    for feature in body["features"]:
        ring = feature["geometry"]["coordinates"][0]
        assert feature["geometry"]["type"] == "Polygon"
        assert ring[0] == ring[-1]


def test_hotspots_geojson_respects_bbox(api) -> None:
    body = api("/api/v1/map/hotspots?bbox=95,55,105,62").json()

    assert body["type"] == "FeatureCollection"
    assert body["meta"]["crs"] == "EPSG:4326"
    assert body["features"]
    for feature in body["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert 95 <= lon <= 105 and 55 <= lat <= 62
        assert isinstance(feature["properties"]["t"], int)


def test_hotspots_are_aggregated_at_country_zoom(api) -> None:
    full = api("/api/v1/map/hotspots").json()
    aggregated = api("/api/v1/map/hotspots?zoom=2").json()

    assert aggregated["meta"]["aggregated"] is True
    assert len(aggregated["features"]) < len(full["features"])
    assert sum(item["properties"]["count"] for item in aggregated["features"]) == len(
        full["features"]
    )


def test_map_layers_are_valid_feature_collections(api) -> None:
    for path in (
        "incidents",
        "perimeters",
        "burn-scars",
        "risk-objects",
        "thermal-sources",
        "wind",
        "clouds",
    ):
        response = api(f"/api/v1/map/{path}?bbox=60,40,180,80")
        body = response.json()
        assert response.status_code == 200, path
        assert body["type"] == "FeatureCollection"
        assert body["meta"]["count"] == len(body["features"])


def test_burn_scars(api) -> None:
    listing = api("/api/v1/burn-scars").json()
    scar = api("/api/v1/burn-scars/BS-2026-064").json()

    assert listing["items"][0]["area_ha"] >= listing["items"][-1]["area_ha"]
    assert scar["area_ha"] == 814
    assert {zone["severity"]: zone["area_ha"] for zone in scar["zones"]} == {
        "low": 122,
        "moderate": 391,
        "high": 301,
    }
    assert api("/api/v1/burn-scars/BS-0000-000").status_code == 404


def test_analytics_summary(api) -> None:
    body = api("/api/v1/analytics/summary?region=krasnoyarsk&from=2026-06-01&to=2026-09-01").json()

    assert body["totals"]["incidents"] == sum(point["incidents"] for point in body["series"])
    assert [region["region_id"] for region in body["regions"]] == ["krasnoyarsk"]
    assert all(scar["region_id"] == "krasnoyarsk" for scar in body["largest_burn_scars"])


def test_observation_histogram(api) -> None:
    query = "bins=24&from=2026-09-15T12:00:00Z&to=2026-09-16T12:00:00Z"
    body = api(f"/api/v1/observations/histogram?{query}").json()
    incident = sum(item["incident"] for item in body["bins"])

    assert len(body["bins"]) == 24
    assert 0 < incident <= sum(item["total"] for item in body["bins"])
