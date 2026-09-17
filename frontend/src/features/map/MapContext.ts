"use client";

import { createContext, useContext } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";

import type { OperationalLayers } from "./layers";

export interface MapContextValue {
  map: MapLibreMap | null;
  styleVersion: number;
  layers: OperationalLayers;
}

export const MapContext = createContext<MapContextValue | null>(null);

export function useMapContext(): MapContextValue {
  const value = useContext(MapContext);
  if (!value) throw new Error("useMapContext must be used inside KromaMap");
  return value;
}
