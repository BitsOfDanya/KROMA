"use client";

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api/client";
import type { LngLatBounds } from "maplibre-gl";
import { useEffect, useMemo, useState } from "react";

import { useFilteredIncidents } from "@/features/incidents/useFilteredIncidents";
import { api } from "@/lib/api/endpoints";
import {
  useHotspots,
  useIncidentForecast,
  useLiveHotspots,
  useLiveIncidents,
  useMapLayer,
} from "@/lib/api/queries";
import type { BBox, FeatureCollection } from "@/lib/api/types";
import { snapBBox } from "@/lib/geo";
import { incidentStateAtIndex, parseStateKey, stateKey } from "@/lib/replay";
import { useWorkspace } from "@/state/workspace";

import { AOI_SOURCE } from "./layers/aoi";
import { CHIPS_POINTS_SOURCE, CHIPS_SOURCE } from "./layers/chips";
import { BURN_SCARS_SOURCE } from "./layers/burnScars";
import { CLOUDS_SOURCE, WIND_SOURCE } from "./layers/environment";
import { FORECAST_SOURCE } from "./layers/forecast";
import { HOTSPOTS_SOURCE } from "./layers/hotspots";
import {
  INCIDENT_SELECTED_LAYERS,
  INCIDENTS_PRIORITY_SOURCE,
  INCIDENTS_SOURCE,
} from "./layers/incidents";
import { PERIMETERS_SOURCE } from "./layers/perimeters";
import { RISK_SOURCE } from "./layers/riskObjects";
import { THERMAL_SOURCE } from "./layers/thermal";
import { emptyCollection } from "./layers/types";
import { useMapContext } from "./MapContext";
import { enrichWindCollection } from "./windField";

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
  const [viewport, setViewport] = useState<{
    bbox: BBox;
    aggregated: boolean;
  } | null>(null);

  useEffect(() => {
    if (!map) return;
    const update = () => {
      const bbox = snapBBox(boundsToBBox(map.getBounds()));
      const aggregated = map.getZoom() < AGGREGATION_ZOOM;
      setViewport((previous) =>
        previous &&
        previous.aggregated === aggregated &&
        previous.bbox.every((value, index) => value === bbox[index])
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
      if (state.cursor !== null && state.playing && now - throttle < 110)
        return;
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

function LiveIncidentSources({ bbox }: { bbox: BBox | null }) {
  const live = useLiveIncidents(bbox, true);
  const collections = useMemo(() => {
    const features =
      (live.data as FeatureCollection<{ severity: string }> | undefined)
        ?.features ?? [];
    const regular: GeoJSON.Feature[] = [];
    const priority: GeoJSON.Feature[] = [];
    for (const feature of features) {
      (feature.properties.severity === "critical" ? priority : regular).push(
        feature as GeoJSON.Feature,
      );
    }
    return {
      regular: {
        type: "FeatureCollection",
        features: regular,
      } as GeoJSON.FeatureCollection,
      priority: {
        type: "FeatureCollection",
        features: priority,
      } as GeoJSON.FeatureCollection,
    };
  }, [live.data]);

  useSource(INCIDENTS_SOURCE, collections.regular);
  useSource(INCIDENTS_PRIORITY_SOURCE, collections.priority);
  return null;
}

function ReplayIncidentSources() {
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
      const state = incidentStateAtIndex(
        incident,
        indices ? indices[position] : null,
      );
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
      if (state.severity === "critical" || incident.id === selectedId)
        priority.push(feature);
      else regular.push(feature);
    });
    return {
      regular: {
        type: "FeatureCollection",
        features: regular,
      } as GeoJSON.FeatureCollection,
      priority: {
        type: "FeatureCollection",
        features: priority,
      } as GeoJSON.FeatureCollection,
    };
  }, [items, key, selectedId]);

  useSource(INCIDENTS_SOURCE, collections.regular);
  useSource(INCIDENTS_PRIORITY_SOURCE, collections.priority);

  useEffect(() => {
    if (!map) return;
    for (const layer of INCIDENT_SELECTED_LAYERS) {
      if (map.getLayer(layer))
        map.setFilter(layer, ["==", ["get", "id"], selectedId ?? ""]);
    }
  }, [map, selectedId, styleVersion]);

  return null;
}

function IncidentSources({
  appMode,
  bbox,
}: {
  appMode: "live" | "replay";
  bbox: BBox | null;
}) {
  if (appMode === "live") return <LiveIncidentSources bbox={bbox} />;
  return <ReplayIncidentSources />;
}

function ForecastSource() {
  const appMode = useWorkspace((state) => state.appMode);
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const forecast = useIncidentForecast(
    appMode === "replay" ? selectedId : null,
  );
  const data =
    appMode === "replay" && selectedId
      ? (forecast.data as GeoJSON.GeoJSON | undefined)
      : emptyCollection();
  useSource(FORECAST_SOURCE, data);
  return null;
}

function LiveHotspotSource({
  bbox,
  enabled,
}: {
  bbox: BBox | null;
  enabled: boolean;
}) {
  const hotspots = useLiveHotspots(bbox, enabled);
  const data = enabled
    ? (hotspots.data as GeoJSON.GeoJSON | undefined)
    : emptyCollection();
  useSource(HOTSPOTS_SOURCE, data);
  return null;
}

function ReplayLayerSources({
  bbox,
  aggregated,
}: {
  bbox: BBox | null;
  aggregated: boolean;
}) {
  const layers = useWorkspace((state) => state.layers);
  const evidenceMode = useWorkspace((state) => state.evidenceMode);
  const [hotspotsFrom] = useState(
    () =>
      new Date(Date.now() - HOTSPOT_WINDOW_MS).toISOString().slice(0, 13) +
      ":00:00Z",
  );

  const hotspots = useHotspots(bbox, aggregated, hotspotsFrom);
  const perimeters = useMapLayer(
    "perimeters",
    bbox,
    api.map.perimeters,
    evidenceMode === "events",
  );
  const burnScars = useMapLayer(
    "burn-scars",
    bbox,
    api.map.burnScars,
    layers.burnScars,
  );
  const risk = useMapLayer(
    "risk-objects",
    bbox,
    (value, signal) => api.map.riskObjects(value, undefined, signal),
    layers.settlements ||
      layers.roads ||
      layers.infrastructure ||
      layers.protectedAreas,
  );
  const thermal = useMapLayer(
    "thermal-sources",
    bbox,
    api.map.thermalSources,
    layers.thermalMemory,
  );
  const wind = useMapLayer("wind", bbox, api.map.wind, layers.wind);
  const clouds = useMapLayer("clouds", bbox, api.map.clouds, layers.clouds);

  const asGeoJSON = (collection?: FeatureCollection<unknown>) =>
    collection as GeoJSON.GeoJSON | undefined;
  useSource(HOTSPOTS_SOURCE, asGeoJSON(hotspots.data));
  useSource(PERIMETERS_SOURCE, asGeoJSON(perimeters.data));
  useSource(BURN_SCARS_SOURCE, asGeoJSON(burnScars.data));
  useSource(RISK_SOURCE, asGeoJSON(risk.data));
  useSource(THERMAL_SOURCE, asGeoJSON(thermal.data));
  useSource(
    WIND_SOURCE,
    enrichWindCollection(
      wind.data as
        | FeatureCollection<{
            from_deg?: number;
            to_deg?: number;
            speed_ms?: number;
          }>
        | undefined,
    ),
  );
  useSource(CLOUDS_SOURCE, asGeoJSON(clouds.data));
  return null;
}

function AoiSource() {
  const [data, setData] = useState<GeoJSON.GeoJSON>(emptyCollection());
  useEffect(() => {
    let cancelled = false;
    void fetch("/data/fire_monitoring_aoi.geojson")
      .then((response) => {
        if (!response.ok) throw new Error(`AOI HTTP ${response.status}`);
        return response.json();
      })
      .then((collection: GeoJSON.FeatureCollection) => {
        if (cancelled) return;
        setData({
          type: "FeatureCollection",
          features: (collection.features ?? []).map((feature) => ({
            ...feature,
            properties: {
              ...(feature.properties ?? {}),
              feature_id: String(
                feature.id ??
                  (feature.properties as { id?: string } | null)?.id ??
                  "",
              ),
              name: String(
                (feature.properties as { name?: string } | null)?.name ??
                  feature.id ??
                  "",
              ),
            },
          })),
        });
      })
      .catch(() => {
        if (!cancelled) setData(emptyCollection());
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useSource(AOI_SOURCE, data);
  return null;
}

function ChipsSource() {
  const [data, setData] = useState<GeoJSON.GeoJSON>(emptyCollection());
  useEffect(() => {
    let cancelled = false;
    void fetch("/data/monitoring_chips.geojson")
      .then((response) => {
        if (!response.ok) throw new Error(`chips HTTP ${response.status}`);
        return response.json();
      })
      .then((collection: GeoJSON.FeatureCollection) => {
        if (!cancelled) setData(collection);
      })
      .catch(() => {
        if (!cancelled) setData(emptyCollection());
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const points = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        data.type === "FeatureCollection"
          ? data.features.flatMap((feature) => {
              if (feature.geometry.type !== "Polygon") return [];
              const ring = feature.geometry.coordinates[0].slice(0, -1);
              return [
                {
                  ...feature,
                  geometry: {
                    type: "Point" as const,
                    coordinates: [
                      ring.reduce((sum, p) => sum + p[0], 0) / ring.length,
                      ring.reduce((sum, p) => sum + p[1], 0) / ring.length,
                    ],
                  },
                },
              ];
            })
          : [],
    }),
    [data],
  );
  useSource(CHIPS_SOURCE, data);
  useSource(CHIPS_POINTS_SOURCE, points);
  return null;
}

function TrainValidationSource() {
  const chipId = useWorkspace((state) => state.selectedTrainChipId);
  const layer = useWorkspace((state) => state.trainValidationLayer);
  const { map, styleVersion } = useMapContext();
  const query = useQuery({
    queryKey: ["train-map", chipId, layer, "v006"],
    queryFn: ({ signal }) =>
      apiGet<GeoJSON.FeatureCollection>(
        `/api/v1/datasets/train/${chipId}/geometry`,
        { layer },
        signal,
      ),
    enabled: Boolean(chipId),
    staleTime: Infinity,
    retry: false,
  });
  useSource("k-chip-validation", query.data ?? emptyCollection());
  useEffect(() => {
    if (!map || !map.getSource(CHIPS_SOURCE)) return;
    map.removeFeatureState({ source: CHIPS_SOURCE });
    if (chipId)
      map.setFeatureState(
        { source: CHIPS_SOURCE, id: chipId },
        { selected: true },
      );
  }, [map, styleVersion, chipId]);
  return chipId ? (
    <div
      role="status"
      style={{
        position: "absolute",
        top: 66,
        left: "50%",
        zIndex: 5,
        background: "var(--surface)",
        padding: 8,
        borderRadius: 8,
      }}
    >
      {chipId} ·{" "}
      {query.isPending
        ? "Загрузка…"
        : query.isError
          ? "Геометрии недоступны"
          : layer.toUpperCase()}
    </div>
  ) : null;
}

export function MapDataSync() {
  const viewport = useViewport();
  const bbox = viewport?.bbox ?? null;
  const appMode = useWorkspace((state) => state.appMode);

  useReplayClock();

  return (
    <>
      <AoiSource />
      <ChipsSource />
      <TrainValidationSource />
      <IncidentSources appMode={appMode} bbox={bbox} />
      <ForecastSource />
      {appMode === "live" ? (
        <LiveHotspotSource
          bbox={bbox}
          enabled={!(viewport?.aggregated ?? true)}
        />
      ) : (
        <ReplayLayerSources
          bbox={bbox}
          aggregated={viewport?.aggregated ?? false}
        />
      )}
    </>
  );
}
