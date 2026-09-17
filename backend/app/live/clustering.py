import hashlib
from dataclasses import dataclass, field

from kroma_geo.measure import bbox_of, haversine_km

from app.live.models import LiveDetection, LiveIncident
from app.services.incidents import severity_for


@dataclass
class _Cluster:
    members: list[LiveDetection] = field(default_factory=list)
    lon_sum: float = 0.0
    lat_sum: float = 0.0

    def add(self, detection: LiveDetection) -> None:
        self.members.append(detection)
        self.lon_sum += detection.location[0]
        self.lat_sum += detection.location[1]

    @property
    def centroid(self) -> tuple[float, float]:
        count = len(self.members)
        return (self.lon_sum / count, self.lat_sum / count)


def cluster_detections(
    detections: list[LiveDetection], radius_km: float, window_hours: float
) -> list[LiveIncident]:
    ordered = sorted(detections, key=lambda item: item.acquired_at)
    clusters: list[_Cluster] = []
    for detection in ordered:
        match: _Cluster | None = None
        for cluster in clusters:
            last_seen = max(member.acquired_at for member in cluster.members)
            hours_gap = abs((detection.acquired_at - last_seen).total_seconds()) / 3600
            if hours_gap > window_hours:
                continue
            if haversine_km(cluster.centroid, detection.location) <= radius_km:
                match = cluster
                break
        if match is None:
            match = _Cluster()
            clusters.append(match)
        match.add(detection)

    incidents: list[LiveIncident] = []
    for cluster in clusters:
        members = cluster.members
        first_detected_at = min(member.acquired_at for member in members)
        updated_at = max(member.acquired_at for member in members)
        frp_total = sum(member.frp_mw or 0 for member in members)
        high_confidence_share = sum(
            1 for member in members if member.source_confidence == "h"
        ) / len(members)
        count = len(members)
        priority = min(
            99,
            round(18 + count * 4 + min(frp_total, 320) / 320 * 55 + high_confidence_share * 22),
        )
        status = "confirmed" if count >= 2 else "suspected"
        hours_since_update = (
            max(m.acquired_at for m in ordered) - updated_at
        ).total_seconds() / 3600
        if status == "confirmed" and hours_since_update > 24:
            status = "monitoring"
        centroid = tuple(round(value, 5) for value in cluster.centroid)
        bbox = bbox_of([member.location for member in members])
        cluster_key = f"{round(centroid[0], 1)}:{round(centroid[1], 1)}"
        cluster_id = f"LV-{hashlib.sha256(cluster_key.encode()).hexdigest()[:6].upper()}"
        incidents.append(
            LiveIncident(
                id=cluster_id,
                status=status,
                severity=severity_for(priority),
                priority=priority,
                centroid=centroid,
                bbox=bbox,
                first_detected_at=first_detected_at,
                updated_at=updated_at,
                detection_count=count,
                frp_mw=round(frp_total, 1),
                sources=tuple(sorted({member.satellite for member in members})),
            )
        )
    return incidents
