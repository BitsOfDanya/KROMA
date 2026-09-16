"use client";

import type { LngLatBounds } from "maplibre-gl";
import { useEffect, useMemo, useState } from "react";

import { useFilteredIncidents } from "@/features/incidents/useFilteredIncidents";
import { api } from "@/lib/api/endpoints";
import { useHotspots, useIncidentForecast, useMapLayer } from "@/lib/api/queries";
import type { BBox, FeatureCollection } from "@/lib/api/types";
import { snapBBox } from "@/lib/geo";
import { incidentStateAtIndex, parseStateKey, stateKey } from "@/lib/replay";
import { useWorkspace } from "@/state/workspace";

import { BURN_SCARS_SOURCE } from "./layers/burnScars";
import { CLOUDS_SOURCE, WIND_SOURCE } from "./layers/environment";
import { FORECAST_SOURCE } from "./layers/forecast";
import { HOTSPOTS_SOURCE } from "./layers/hotspots";
import { INCIDENT_SELECTED_LAYERS, INCIDENTS_PRIORITY_SOURCE, INCIDENTS_SOURCE } from "./layers/incidents";
import { PERIMETERS_SOURCE } from "./layers/perimeters";
import { RISK_SOURCE } from "./layers/riskObjects";
import { THERMAL_SOURCE } from "./layers/thermal";
import { emptyCollection } from "./layers/types";
import { useMapContext } from "./MapContext";

const AGGREGATION_ZOOM = 3;
const HOTSPOT_WINDOW_MS = 7 * 24 * 3_600_000;

function boundsToBBox(bounds: LngLatBounds): BBox {
  return [
    Math.max(-180, bounds.getWest()),
    Math.max(-85, bounds.getSouth()),
    Math.min(180, bounds.getEast()),
    Math.min(85, bounds.getNorth()),
  ];
}

function useViewport() {
  const { map } = useMapContext();
  const [viewport, setViewport] = useState<{ bbox: BBox; aggregated: boolean } | null>(null);

  useEffect(() => {
    if (!map) return;
    const update = () => {
      const bbox = snapBBox(boundsToBBox(map.getBounds()));
      const aggregated = map.getZoom() < AGGREGATION_ZOOM;
      setViewport((previous) =>
        previous && previous.aggregated === aggregated && previous.bbox.every((value, index) => value === bbox[index])
          ? previous
          : { bbox, aggregated },
      );
    };
    update();
    map.on("moveend", update);
    return () => {
      map.off("moveend", update);
    };
  }, [map]);

  return viewport;
}

function useSource(sourceId: string, data: GeoJSON.GeoJSON | undefined) {
  const { map, styleVersion, layers } = useMapContext();
  useEffect(() => {
    if (!data) return;
    layers.setData(map, sourceId, data);
  }, [map, layers, sourceId, data, styleVersion]);
}

function useReplayClock() {
  const { map, styleVersion } = useMapContext();
  useEffect(() => {
    if (!map) return;
    let throttle = 0;
    const apply = (cursor: number | null) => {
      if (!map.isStyleLoaded()) return;
      const seconds = Math.floor((cursor ?? Date.now()) / 1000);
      map.setGlobalStateProperty("time", seconds);
    };
    apply(useWorkspace.getState().cursor);
    const unsubscribe = useWorkspace.subscribe((state, previous) => {
      if (state.cursor === previous.cursor) return;
      const now = performance.now();
      if (state.cursor !== null && state.playing && now - throttle < 110) return;
      throttle = now;
      apply(state.cursor);
    });
    const live = window.setInterval(() => {
      if (useWorkspace.getState().cursor === null) apply(null);
    }, 30_000);
    return () => {
      unsubscribe();
      window.clearInterval(live);
    };
  }, [map, styleVersion]);
}

function IncidentSources() {
  const { map, styleVersion } = useMapContext();
  const { items } = useFilteredIncidents();
  const cursor = useWorkspace((state) => state.cursor);
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const key = stateKey(items, cursor);

  const collections = useMemo(() => {
    const regular: GeoJSON.Feature[] = [];
    const priority: GeoJSON.Feature[] = [];
    const indices = parseStateKey(key);
    items.forEach((incident, position) => {
      const state = incidentStateAtIndex(incident, indices ? indices[position] : null);
      if (!state.visible) return;
      const feature: GeoJSON.Feature = {
        type: "Feature",
        geometry: { type: "Point", coordinates: incident.centroid },
        properties: {
          id: incident.id,
          status: state.status,
          severity: state.severity,
          priority: state.priority,
          confidence: state.confidence,
          threat: state.threat,
          area_ha: state.area_ha,
          district: incident.district,
        },
      };
      if (state.severity === "critical" || incident.id === selectedId) priority.push(feature);
      else regular.push(feature);
    });
    return {
      regular: { type: "FeatureCollection", features: regular } as GeoJSON.FeatureCollection,
      priority: { type: "FeatureCollection", features: priority } as GeoJSON.FeatureCollection,
    };
  }, [items, key, selectedId]);

  useSource(INCIDENTS_SOURCE, collections.regular);
  useSource(INCIDENTS_PRIORITY_SOURCE, collections.priority);

  useEffect(() => {
    if (!map) return;
    for (const layer of INCIDENT_SELECTED_LAYERS) {
      if (map.getLayer(layer)) map.setFilter(layer, ["==", ["get", "id"], selectedId ?? ""]);
    }
  }, [map, selectedId, styleVersion]);

  return null;
}

function ForecastSource() {
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const forecast = useIncidentForecast(selectedId);
  const data = selectedId ? (forecast.data as GeoJSON.GeoJSON | undefined) : emptyCollection();
  useSource(FORECAST_SOURCE, data);
  return null;
}

export function MapDataSync() {
  const viewport = useViewport();
  const bbox = viewport?.bbox ?? null;
  const layers = useWorkspace((state) => state.layers);
  const evidenceMode = useWorkspace((state) => state.evidenceMode);
  const [hotspotsFrom] = useState(() => new Date(Date.now() - HOTSPOT_WINDOW_MS).toISOString().slice(0, 13) + ":00:00Z");

  useReplayClock();

  const hotspots = useHotspots(bbox, viewport?.aggregated ?? false, hotspotsFrom);
  const perimeters = useMapLayer("perimeters", bbox, api.map.perimeters, evidenceMode === "events");
  const burnScars = useMapLayer("burn-scars", bbox, api.map.burnScars, layers.burnScars);
  const risk = useMapLayer(
    "risk-objects",
    bbox,
    (value, signal) => api.map.riskObjects(value, undefined, signal),
    layers.settlements || layers.roads || layers.infrastructure || layers.protectedAreas,
  );
  const thermal = useMapLayer("thermal-sources", bbox, api.map.thermalSources, layers.thermalMemory);
  const wind = useMapLayer("wind", bbox, api.map.wind, layers.wind);
  const clouds = useMapLayer("clouds", bbox, api.map.clouds, layers.clouds);

  const asGeoJSON = (collection?: FeatureCollection<unknown>) => collection as GeoJSON.GeoJSON | undefined;
  useSource(HOTSPOTS_SOURCE, asGeoJSON(hotspots.data));
  useSource(PERIMETERS_SOURCE, asGeoJSON(perimeters.data));
  useSource(BURN_SCARS_SOURCE, asGeoJSON(burnScars.data));
  useSource(RISK_SOURCE, asGeoJSON(risk.data));
  useSource(THERMAL_SOURCE, asGeoJSON(thermal.data));
  useSource(WIND_SOURCE, asGeoJSON(wind.data));
  useSource(CLOUDS_SOURCE, asGeoJSON(clouds.data));

  return (
    <>
      <IncidentSources />
      <ForecastSource />
    </>
  );
}
