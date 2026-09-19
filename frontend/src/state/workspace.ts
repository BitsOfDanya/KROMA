"use client";

import { create } from "zustand";

import type { BBox, IncidentStatus } from "@/lib/api/types";
import type { ReplaySpeed, TimeWindow } from "@/lib/replay";

export type Panel = "incidents" | "layers" | "filters" | null;
export type BasemapMode = "map" | "satellite" | "terrain";
export type EvidenceMode = "events" | "data";
export type QueueFilter = "all" | "critical" | "confirmed" | "monitoring";
export type AppMode = "live" | "replay";
export type MapProfile = "ops" | "fireWeather";

export type LayerId =
  | "incidents"
  | "rawDetections"
  | "burnScars"
  | "perimeter"
  | "activeFront"
  | "forecastP50"
  | "forecastP80"
  | "forecastP95"
  | "thermalMemory"
  | "settlements"
  | "roads"
  | "infrastructure"
  | "protectedAreas"
  | "wind"
  | "clouds"
  | "monitoringAoi"
  | "monitoringChips";

export type CameraRequest =
  | { kind: "bounds"; bbox: BBox; maxZoom?: number; nonce: number }
  | { kind: "center"; center: [number, number]; zoom: number; nonce: number };

export type CameraRequestInput =
  | { kind: "bounds"; bbox: BBox; maxZoom?: number; nonce?: number }
  | { kind: "center"; center: [number, number]; zoom: number; nonce?: number };

export const DEFAULT_LAYERS: Record<LayerId, boolean> = {
  incidents: true,
  rawDetections: false,
  burnScars: true,
  perimeter: true,
  activeFront: true,
  forecastP50: true,
  forecastP80: true,
  forecastP95: true,
  thermalMemory: false,
  settlements: true,
  roads: true,
  infrastructure: true,
  protectedAreas: false,
  wind: false,
  clouds: false,
  monitoringAoi: true,
  monitoringChips: true,
};

const FIRE_WEATHER_LAYERS: Record<LayerId, boolean> = {
  ...DEFAULT_LAYERS,
  incidents: true,
  rawDetections: false,
  burnScars: true,
  perimeter: true,
  activeFront: true,
  forecastP50: false,
  forecastP80: false,
  forecastP95: false,
  thermalMemory: false,
  settlements: true,
  roads: false,
  infrastructure: false,
  protectedAreas: false,
  wind: true,
  clouds: true,
  monitoringAoi: true,
  monitoringChips: true,
};

interface WorkspaceState {
  appMode: AppMode;
  mapProfile: MapProfile;
  selectedIncidentId: string | null;
  selectedTrainChipId: string | null;
  trainValidationLayer: "gt" | "pred" | "error";
  selectTrainChip: (id: string | null) => void;
  setTrainValidationLayer: (layer: "gt" | "pred" | "error") => void;
  panel: Panel;
  basemap: BasemapMode;
  evidenceMode: EvidenceMode;
  layers: Record<LayerId, boolean>;
  queueFilter: QueueFilter;
  regionId: string | null;
  statusFilter: IncidentStatus[];
  priorityMin: number;
  timeWindow: TimeWindow;
  cursor: number | null;
  playing: boolean;
  speed: ReplaySpeed;
  timelineExpanded: boolean;
  measuring: boolean;
  camera: CameraRequest | null;
  setAppMode: (mode: AppMode) => void;
  setMapProfile: (profile: MapProfile) => void;
  selectIncident: (id: string | null) => void;
  togglePanel: (panel: Exclude<Panel, null>) => void;
  closePanel: () => void;
  setBasemap: (mode: BasemapMode) => void;
  setEvidenceMode: (mode: EvidenceMode) => void;
  toggleLayer: (id: LayerId) => void;
  setLayer: (id: LayerId, visible: boolean) => void;
  setQueueFilter: (filter: QueueFilter) => void;
  setRegion: (regionId: string | null) => void;
  toggleStatus: (status: IncidentStatus) => void;
  setPriorityMin: (value: number) => void;
  resetFilters: () => void;
  setTimeWindow: (window: TimeWindow) => void;
  setCursor: (cursor: number | null) => void;
  setPlaying: (playing: boolean) => void;
  setSpeed: (speed: ReplaySpeed) => void;
  toggleTimelineExpanded: () => void;
  setMeasuring: (measuring: boolean) => void;
  requestCamera: (request: CameraRequestInput) => void;
}

let cameraNonce = 0;

export const useWorkspace = create<WorkspaceState>((set) => ({
  appMode: "replay",
  mapProfile: "ops",
  selectedIncidentId: null,
  selectedTrainChipId: null,
  trainValidationLayer: "pred",
  selectTrainChip: (selectedTrainChipId) => set({ selectedTrainChipId }),
  setTrainValidationLayer: (trainValidationLayer) =>
    set({ trainValidationLayer }),
  panel: "incidents",
  basemap: "map",
  evidenceMode: "events",
  layers: DEFAULT_LAYERS,
  queueFilter: "all",
  regionId: null,
  statusFilter: [],
  priorityMin: 0,
  timeWindow: "24h",
  cursor: null,
  playing: false,
  speed: 4,
  timelineExpanded: false,
  measuring: false,
  camera: null,
  setAppMode: (appMode) =>
    set({
      appMode,
      selectedIncidentId: null,
      playing: false,
      cursor: null,
      panel: "incidents",
      mapProfile: "ops",
    }),
  setMapProfile: (mapProfile) =>
    set((state) =>
      mapProfile === "fireWeather"
        ? {
            mapProfile,
            basemap: "terrain",
            evidenceMode: "events",
            layers: { ...FIRE_WEATHER_LAYERS },
            measuring: false,
          }
        : {
            mapProfile,
            basemap: state.basemap === "terrain" ? "map" : state.basemap,
            layers: { ...DEFAULT_LAYERS },
          },
    ),
  selectIncident: (id) => set({ selectedIncidentId: id }),
  togglePanel: (panel) =>
    set((state) => ({ panel: state.panel === panel ? null : panel })),
  closePanel: () => set({ panel: null }),
  setBasemap: (basemap) => set({ basemap }),
  setEvidenceMode: (evidenceMode) =>
    set((state) => ({
      evidenceMode,
      layers: {
        ...state.layers,
        rawDetections: evidenceMode === "data",
        incidents: true,
      },
    })),
  toggleLayer: (id) =>
    set((state) => {
      const layers = { ...state.layers, [id]: !state.layers[id] };
      const evidenceMode =
        id === "rawDetections"
          ? layers.rawDetections
            ? "data"
            : "events"
          : state.evidenceMode;
      return { layers, evidenceMode, mapProfile: "ops" };
    }),
  setLayer: (id, visible) =>
    set((state) => ({
      layers: { ...state.layers, [id]: visible },
      mapProfile: "ops",
    })),
  setQueueFilter: (queueFilter) => set({ queueFilter }),
  setRegion: (regionId) => set({ regionId }),
  toggleStatus: (status) =>
    set((state) => ({
      statusFilter: state.statusFilter.includes(status)
        ? state.statusFilter.filter((item) => item !== status)
        : [...state.statusFilter, status],
    })),
  setPriorityMin: (priorityMin) => set({ priorityMin }),
  resetFilters: () => set({ statusFilter: [], priorityMin: 0, regionId: null }),
  setTimeWindow: (timeWindow) => set({ timeWindow }),
  setCursor: (cursor) => set({ cursor }),
  setPlaying: (playing) => set({ playing }),
  setSpeed: (speed) => set({ speed }),
  toggleTimelineExpanded: () =>
    set((state) => ({ timelineExpanded: !state.timelineExpanded })),
  setMeasuring: (measuring) => set({ measuring }),
  requestCamera: (request) => {
    cameraNonce += 1;
    set({ camera: { ...request, nonce: cameraNonce } as CameraRequest });
  },
}));
