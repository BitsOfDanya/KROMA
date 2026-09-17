from app.models.burn_scar import BurnScar
from app.repositories.base import FireDataRepository
from app.schemas.burn_scars import BurnScarList, BurnScarSummary, SeverityBreakdown
from app.services.errors import NotFoundError


def summarize_burn_scar(scar: BurnScar) -> BurnScarSummary:
    areas = {zone.severity: zone.area_ha for zone in scar.zones}
    return BurnScarSummary(
        id=scar.id,
        incident_id=scar.incident_id,
        name=scar.name,
        region_id=scar.region_id,
        region=scar.region,
        district=scar.district,
        centroid=scar.centroid,
        bbox=scar.bbox,
        fire_started_on=scar.fire_started_on,
        fire_ended_on=scar.fire_ended_on,
        assessed_at=scar.assessed_at,
        assessment=scar.assessment,
        area_ha=scar.area_ha,
        dnbr_mean=scar.dnbr_mean,
        severity=SeverityBreakdown(
            low_ha=areas.get("low", 0),
            moderate_ha=areas.get("moderate", 0),
            high_ha=areas.get("high", 0),
        ),
    )


class BurnScarService:
    def __init__(self, repository: FireDataRepository) -> None:
        self.repository = repository

    def list(self, region_id: str | None, min_area_ha: float | None) -> BurnScarList:
        items = [
            summarize_burn_scar(scar)
            for scar in self.repository.burn_scars()
            if (region_id is None or scar.region_id == region_id)
            and (min_area_ha is None or scar.area_ha >= min_area_ha)
        ]
        items.sort(key=lambda item: item.area_ha, reverse=True)
        return BurnScarList(items=items, total=len(items))

    def get(self, burn_scar_id: str) -> BurnScar:
        scar = self.repository.burn_scar(burn_scar_id)
        if scar is None:
            raise NotFoundError("Burn scar", burn_scar_id)
        return scar
