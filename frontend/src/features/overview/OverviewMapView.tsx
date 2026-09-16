"use client";

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { KromaMap, type MapView } from "@/features/map/KromaMap";
import { MapControls } from "@/features/map/MapControls";
import { MapDataSync } from "@/features/map/MapDataSync";
import { MapInteractions } from "@/features/map/MapInteractions";
import { IncidentInspector } from "@/features/incidents/IncidentInspector";
import { IncidentQueue } from "@/features/incidents/IncidentQueue";
import { LayersPanel } from "@/features/layers/LayersPanel";
import { FiltersPanel } from "@/features/layers/FiltersPanel";
import { Timeline } from "@/features/timeline/Timeline";
import { useIncident } from "@/lib/api/queries";
import { parseNumber } from "@/lib/geo";
import { useWorkspace } from "@/state/workspace";

import { EvidenceModeToggle } from "./EvidenceModeToggle";
import { ControlRail } from "./ControlRail";
import styles from "./overview.module.css";

function useUrlSync() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const selectIncident = useWorkspace((state) => state.selectIncident);
  const requestCamera = useWorkspace((state) => state.requestCamera);
  const appliedInitial = useRef(false);
  const detail = useIncident(selectedId);

  useEffect(() => {
    if (appliedInitial.current) return;
    appliedInitial.current = true;
    const incident = searchParams.get("incident");
    if (incident) {
      selectIncident(incident);
      return;
    }
    const lat = parseNumber(searchParams.get("lat"), -85, 85);
    const lng = parseNumber(searchParams.get("lng"), -180, 180);
    const zoom = parseNumber(searchParams.get("zoom"), 2, 15);
    if (lat !== null && lng !== null) {
      requestCamera({ kind: "center", center: [lng, lat], zoom: zoom ?? 6 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (selectedId) params.set("incident", selectedId);
    else params.delete("incident");
    const next = params.toString();
    const current = searchParams.toString();
    if (next !== current) {
      router.replace(next ? `/?${next}` : "/", { scroll: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  useEffect(() => {
    if (selectedId && detail.data) {
      requestCamera({ kind: "bounds", bbox: detail.data.bbox, maxZoom: 12 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, detail.data?.id]);
}

export function OverviewMapView() {
  useUrlSync();
  const panel = useWorkspace((state) => state.panel);
  const selectedId = useWorkspace((state) => state.selectedIncidentId);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      const state = useWorkspace.getState();
      if (state.measuring) state.setMeasuring(false);
      else if (state.selectedIncidentId) state.selectIncident(null);
      else if (state.panel) state.closePanel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onViewChange = (view: MapView) => {
    void view;
  };

  return (
    <div className={styles.workspace} data-inspector={Boolean(selectedId)}>
      <KromaMap onViewChange={onViewChange}>
        <MapControls />
        <MapInteractions />
        <MapDataSync />
      </KromaMap>
      <ControlRail />
      <EvidenceModeToggle />
      {panel && (
        <div className={styles.panelSlot}>
          {panel === "incidents" && <IncidentQueue />}
          {panel === "layers" && <LayersPanel />}
          {panel === "filters" && <FiltersPanel />}
        </div>
      )}
      {selectedId && (
        <div className={styles.inspectorSlot}>
          <IncidentInspector incidentId={selectedId} />
        </div>
      )}
      <Timeline />
    </div>
  );
}
