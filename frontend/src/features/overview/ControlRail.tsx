"use client";

import { History, Layers, ListOrdered, LocateFixed, Ruler, SlidersHorizontal, Wind } from "lucide-react";

import { IconButton } from "@/components/ui/IconButton";
import { useLiveIncidents, useOverview } from "@/lib/api/queries";
import type { FeatureCollection } from "@/lib/api/types";
import { useWorkspace } from "@/state/workspace";

import styles from "./overview.module.css";

const ICON = { size: 17, strokeWidth: 1.7 };

export function ControlRail() {
  const panel = useWorkspace((state) => state.panel);
  const togglePanel = useWorkspace((state) => state.togglePanel);
  const timelineExpanded = useWorkspace((state) => state.timelineExpanded);
  const toggleTimelineExpanded = useWorkspace((state) => state.toggleTimelineExpanded);
  const measuring = useWorkspace((state) => state.measuring);
  const setMeasuring = useWorkspace((state) => state.setMeasuring);
  const statusFilter = useWorkspace((state) => state.statusFilter);
  const priorityMin = useWorkspace((state) => state.priorityMin);
  const overview = useOverview();
  const appMode = useWorkspace((state) => state.appMode);
  const mapProfile = useWorkspace((state) => state.mapProfile);
  const setMapProfile = useWorkspace((state) => state.setMapProfile);
  const liveIncidents = useLiveIncidents(null, appMode === "live");
  const liveCritical = ((liveIncidents.data as FeatureCollection<{ severity: string }> | undefined)?.features ?? []).filter(
    (item) => item.properties.severity === "critical",
  ).length;
  const critical = appMode === "live" ? liveCritical : (overview.data?.counts.critical ?? 0);
  const filtersActive = statusFilter.length > 0 || priorityMin > 0;

  const locate = () => {
    const state = useWorkspace.getState();
    const region = overview.data?.regions.find((item) => item.id === (state.regionId ?? overview.data?.default_region_id));
    if (region) state.requestCamera({ kind: "center", center: region.center, zoom: region.zoom });
  };

  return (
    <nav className={styles.rail} aria-label="Инструменты карты">
      <span style={{ position: "relative" }}>
        <IconButton
          label="События"
          tooltipSide="right"
          active={panel === "incidents"}
          aria-pressed={panel === "incidents"}
          icon={<ListOrdered {...ICON} />}
          onClick={() => togglePanel("incidents")}
        />
        {critical > 0 && panel !== "incidents" && (
          <span className={styles.railBadge} aria-label={`${critical} критических`}>
            {critical}
          </span>
        )}
      </span>
      <IconButton
        label="Слои"
        tooltipSide="right"
        active={panel === "layers"}
        aria-pressed={panel === "layers"}
        icon={<Layers {...ICON} />}
        onClick={() => togglePanel("layers")}
      />
      {appMode === "replay" && (
        <span style={{ position: "relative" }}>
          <IconButton
            label="Фильтры"
            tooltipSide="right"
            active={panel === "filters"}
            aria-pressed={panel === "filters"}
            icon={<SlidersHorizontal {...ICON} />}
            onClick={() => togglePanel("filters")}
          />
          {filtersActive && <span className={styles.railBadge} style={{ minWidth: 7, height: 7, padding: 0, top: 6, right: 6 }} />}
        </span>
      )}
      <IconButton
        label={timelineExpanded ? "Свернуть хронологию" : "Развернуть хронологию"}
        tooltipSide="right"
        active={timelineExpanded}
        aria-pressed={timelineExpanded}
        icon={<History {...ICON} />}
        onClick={toggleTimelineExpanded}
      />
      {appMode === "replay" && (
        <IconButton
          label={mapProfile === "fireWeather" ? "Выйти из погодного режима" : "Погодный контекст"}
          tooltipSide="right"
          active={mapProfile === "fireWeather"}
          aria-pressed={mapProfile === "fireWeather"}
          icon={<Wind {...ICON} />}
          onClick={() => setMapProfile(mapProfile === "fireWeather" ? "ops" : "fireWeather")}
        />
      )}
      <div className={styles.railDivider} />
      <IconButton label="К региону" tooltipSide="right" icon={<LocateFixed {...ICON} />} onClick={locate} />
      <IconButton
        label={measuring ? "Завершить измерение" : "Измерить расстояние"}
        tooltipSide="right"
        active={measuring}
        aria-pressed={measuring}
        icon={<Ruler {...ICON} />}
        onClick={() => setMeasuring(!measuring)}
      />
    </nav>
  );
}
