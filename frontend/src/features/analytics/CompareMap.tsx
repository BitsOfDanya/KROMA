"use client";

import { Map as MapLibreMap } from "maplibre-gl";

import "@/features/map/mapWorker";
import { useEffect, useRef } from "react";

import { mapProviders } from "@/config/map";
import type { BurnScar } from "@/lib/api/types";

interface CompareMapProps {
  scar: BurnScar;
  variant: "before" | "after";
}

const SEVERITY_COLOR: Record<string, string> = {
  low: "#c49a6c",
  moderate: "#b0603f",
  high: "#7b2624",
};

export function CompareMap({ scar, variant }: CompareMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const [minLon, minLat, maxLon, maxLat] = scar.bbox;
    const source = variant === "before" ? mapProviders.comparisonBefore : mapProviders.satellite;
    const map = new MapLibreMap({
      container,
      style: {
        version: 8,
        sources: { imagery: { type: "raster", ...source } },
        layers: [{ id: "imagery", type: "raster", source: "imagery" }],
      },
      bounds: [
        [minLon, minLat],
        [maxLon, maxLat],
      ],
      fitBoundsOptions: { padding: 12 },
      interactive: false,
      attributionControl: false,
    });

    map.on("load", () => {
      if (variant !== "after") return;
      map.addSource("severity", { type: "geojson", data: scar.geometry as GeoJSON.GeoJSON });
      map.addLayer({
        id: "severity-outline",
        type: "line",
        source: "severity",
        paint: { "line-color": "#f4f1ea", "line-width": 1, "line-opacity": 0.6 },
      });
      for (const zone of scar.zones) {
        const id = `zone-${zone.severity}`;
        if (map.getSource(id)) continue;
        map.addSource(id, { type: "geojson", data: zone.geometry as GeoJSON.GeoJSON });
        map.addLayer({
          id,
          type: "fill",
          source: id,
          paint: { "fill-color": SEVERITY_COLOR[zone.severity] ?? "#7b2624", "fill-opacity": 0.55 },
        });
      }
    });

    return () => map.remove();
  }, [scar, variant]);

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} aria-hidden="true" />;
}
