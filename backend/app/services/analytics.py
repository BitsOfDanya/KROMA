from collections import defaultdict
from datetime import date, timedelta

from app.repositories.base import FireDataRepository
from app.schemas.analytics import AnalyticsSummary, AnalyticsTotals, RegionBreakdown, WeeklyPoint
from app.services.burn_scars import summarize_burn_scar


class AnalyticsService:
    def __init__(self, repository: FireDataRepository) -> None:
        self.repository = repository

    def summary(
        self, start: date | None, end: date | None, region_id: str | None
    ) -> AnalyticsSummary:
        stats = self.repository.weekly_stats()
        end = end or self.repository.reference_time().date()
        start = start or min((item.week_start for item in stats), default=end - timedelta(days=90))
        selected = [
            item
            for item in stats
            if start - timedelta(days=6) <= item.week_start <= end
            and (region_id is None or item.region_id == region_id)
        ]

        weekly: dict[date, list] = defaultdict(list)
        for item in selected:
            weekly[item.week_start].append(item)
        series = []
        for week_start in sorted(weekly):
            items = weekly[week_start]
            incidents = sum(item.incidents for item in items)
            series.append(
                WeeklyPoint(
                    week_start=week_start,
                    incidents=incidents,
                    burned_area_ha=round(sum(item.burned_area_ha for item in items)),
                    high_severity_ha=round(sum(item.high_severity_ha for item in items)),
                    mean_confirmation_minutes=round(
                        sum(item.mean_confirmation_minutes * item.incidents for item in items)
                        / max(incidents, 1),
                        1,
                    ),
                )
            )

        names = {region.id: region.name for region in self.repository.regions()}
        by_region: dict[str, list] = defaultdict(list)
        for item in selected:
            by_region[item.region_id].append(item)
        regions = sorted(
            (
                RegionBreakdown(
                    region_id=key,
                    name=names.get(key, key),
                    incidents=sum(item.incidents for item in items),
                    burned_area_ha=round(sum(item.burned_area_ha for item in items)),
                    high_severity_ha=round(sum(item.high_severity_ha for item in items)),
                )
                for key, items in by_region.items()
            ),
            key=lambda value: value.burned_area_ha,
            reverse=True,
        )

        incidents = sum(item.incidents for item in selected)
        burned = sum(item.burned_area_ha for item in selected)
        high = sum(item.high_severity_ha for item in selected)
        confirmation = sum(item.mean_confirmation_minutes * item.incidents for item in selected)
        scars = [
            summarize_burn_scar(scar)
            for scar in self.repository.burn_scars()
            if (region_id is None or scar.region_id == region_id)
            and scar.fire_started_on <= end
            and (scar.fire_ended_on or end) >= start
        ]
        scars.sort(key=lambda item: item.area_ha, reverse=True)

        return AnalyticsSummary(
            start=start,
            end=end,
            region_id=region_id,
            totals=AnalyticsTotals(
                incidents=incidents,
                burned_area_ha=round(burned),
                high_severity_ha=round(high),
                high_severity_share=round(high / burned, 3) if burned else 0,
                mean_confirmation_minutes=round(confirmation / incidents, 1) if incidents else 0,
            ),
            series=series,
            regions=regions,
            largest_burn_scars=scars[:10],
        )
