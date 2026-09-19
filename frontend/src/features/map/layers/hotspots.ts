import type { ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";

import { FONT_BOLD } from "../basemap";
import { emptyCollection, TIME, type LayerModule } from "./types";

export const HOTSPOTS_SOURCE = "k-hotspots";
export const HOTSPOT_CLUSTER_LAYER = `${HOTSPOTS_SOURCE}-cluster`;
export const HOTSPOT_POINT_LAYER = `${HOTSPOTS_SOURCE}-point`;
export const INCIDENT_OBSERVATION_LAYER = `${HOTSPOTS_SOURCE}-incident`;

const isCluster: ExpressionSpecification = ["any", ["has", "point_count"], ["==", ["get", "classification"], "aggregate"]];
const detections: ExpressionSpecification = ["coalesce", ["get", "detections"], ["get", "count"], 1];
const notFuture: ExpressionSpecification = ["<=", ["get", "t"], TIME];

export const hotspotsModule: LayerModule = {
  sources: {
    [HOTSPOTS_SOURCE]: {
      type: "geojson",
      data: emptyCollection(),
      cluster: true,
      clusterRadius: 42,
      clusterMaxZoom: 7,
      clusterProperties: { detections: ["+", ["coalesce", ["get", "count"], 1]] },
    },
  },
  layers: (palette) => {
    const color: ExpressionSpecification = [
      "case",
      [">", ["get", "t"], ["-", TIME, ["global-state", "freshWindow"]]],
      palette["observation-fresh"],
      palette["incident-high"],
    ];
    const confidenceOpacity: ExpressionSpecification = ["match", ["get", "confidence"], "h", 0.95, "n", 0.72, 0.45];
    return [
      {
        placement: "over-labels",
        visible: (context) => context.evidenceMode === "data",
        spec: {
          id: HOTSPOT_CLUSTER_LAYER,
          type: "circle",
          source: HOTSPOTS_SOURCE,
          filter: isCluster,
          paint: {
            "circle-color": palette.observation,
            "circle-opacity": 0.14,
            "circle-radius": ["step", detections, 10, 10, 13, 50, 17, 200, 22, 600, 27],
            "circle-stroke-color": palette.observation,
            "circle-stroke-width": 1,
            "circle-stroke-opacity": 0.65,
          },
        },
      },
      {
        placement: "over-labels",
        visible: (context) => context.evidenceMode === "data",
        spec: {
          id: `${HOTSPOTS_SOURCE}-cluster-count`,
          type: "symbol",
          source: HOTSPOTS_SOURCE,
          filter: isCluster,
          layout: {
            "text-field": ["to-string", detections],
            "text-font": FONT_BOLD,
            "text-size": 10.5,
            "text-allow-overlap": true,
          },
          paint: { "text-color": palette.text, "text-halo-color": palette["map-label-halo"], "text-halo-width": 1 },
        },
      },
      {
        placement: "over-labels",
        visible: (context) => context.evidenceMode === "data",
        spec: {
          id: HOTSPOT_POINT_LAYER,
          type: "symbol",
          source: HOTSPOTS_SOURCE,
          filter: ["all", ["!", isCluster], notFuture],
          layout: {
            "icon-image": "k-flame",
            "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.28, 8, 0.4, 12, 0.52],
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
            "icon-anchor": "bottom",
          },
          paint: {
            "icon-color": color,
            "icon-opacity": confidenceOpacity,
            "icon-halo-color": palette["map-background"],
            "icon-halo-width": 0.8,
          },
        },
      },
      {
        placement: "over-labels",
        visible: (context) => context.evidenceMode === "events" && context.layers.incidents,
        spec: {
          id: INCIDENT_OBSERVATION_LAYER,
          type: "symbol",
          source: HOTSPOTS_SOURCE,
          minzoom: 8,
          filter: ["all", ["!", isCluster], ["==", ["get", "classification"], "incident"], notFuture],
          layout: {
            "icon-image": "k-flame",
            "icon-size": ["interpolate", ["linear"], ["zoom"], 8, 0.22, 10, 0.32, 13, 0.42],
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
            "icon-anchor": "bottom",
          },
          paint: {
            "icon-color": color,
            "icon-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.55, 10, 0.9],
            "icon-halo-color": palette["map-background"],
            "icon-halo-width": 0.7,
          },
        },
      },
    ];
  },
};
