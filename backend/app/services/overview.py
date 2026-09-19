from datetime import UTC, datetime, timedelta

from app.repositories.base import FireDataRepository, ObservationQuery
from app.schemas.overview import Overview
from app.services.incidents import ACTIVE_STATUSES, IncidentService


class OverviewService:
    def __init__(self, repository: FireDataRepository) -> None:
        self.repository = repository
        self.incidents = IncidentService(repository)

    def overview(self) -> Overview:
        reference = self.repository.reference_time()
        summaries = self.incidents.all_summaries()
        recent = self.repository.observations(
            ObservationQuery(start=reference - timedelta(days=7), end=reference)
        )
        last_day = [item for item in recent if item.acquired_at >= reference - timedelta(hours=24)]
        active = [item for item in summaries if item.status in ACTIVE_STATUSES]
        top = max(active, key=lambda item: item.priority, default=None)
        return Overview(
            generated_at=datetime.now(UTC),
            reference_time=reference,
            data_source="demo",
            regions=self.repository.regions(),
            default_region_id="aoi",
            counts=self.incidents.counts(summaries),
            observations_24h=len(last_day),
            raw_detections_7d=len(recent),
            last_observation_at=max((item.acquired_at for item in recent), default=None),
            top_incident_id=top.id if top else None,
        )
