import type { ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";

import { FONT_BOLD } from "../basemap";
import type { Palette } from "../palette";
import { emptyCollection, severityColor, type LayerModule, type OperationalLayer, type VisibilityContext } from "./types";

export const INCIDENTS_SOURCE = "k-incidents";
export const INCIDENTS_PRIORITY_SOURCE = "k-incidents-priority";
export const INCIDENT_PULSE_LAYER = `${INCIDENTS_PRIORITY_SOURCE}-pulse`;
export const INCIDENT_CLUSTER_LAYER = `${INCIDENTS_SOURCE}-cluster`;
export const INCIDENT_SELECTED_LAYERS = [`${INCIDENTS_SOURCE}-selected`, `${INCIDENTS_PRIORITY_SOURCE}-selected`];

const visibleInEvents = (context: VisibilityContext) => context.evidenceMode === "events" && context.layers.incidents;
const unclustered: ExpressionSpecification = ["!", ["has", "point_count"]];

function statusValue(values: Record<"suspected" | "confirmed" | "monitoring" | "localized", number>): ExpressionSpecification {
  return [
    "match",
    ["get", "status"],
    "suspected",
    values.suspected,
    "monitoring",
    values.monitoring,
    "localized",
    values.localized,
    values.confirmed,
  ];
}

function incidentColor(palette: Palette): ExpressionSpecification {
  return ["case", ["==", ["get", "status"], "localized"], palette["incident-localized"], severityColor(palette)];
}

function markerLayers(source: string, palette: Palette): OperationalLayer[] {
  const color = incidentColor(palette);
  const hover: ExpressionSpecification = ["boolean", ["feature-state", "hover"], false];
  return [
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-halo`,
        type: "circle",
        source,
        filter: ["all", unclustered, ["==", ["get", "status"], "confirmed"]],
        paint: {
          "circle-color": color,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 10, 10, 17],
          "circle-opacity": ["case", ["==", ["get", "severity"], "critical"], 0.2, 0.13],
          "circle-blur": 0.55,
          "circle-pitch-alignment": "map",
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-ring-outer`,
        type: "circle",
        source,
        filter: ["all", unclustered, ["==", ["get", "severity"], "critical"], ["!=", ["get", "status"], "localized"]],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 11.5, 10, 15],
          "circle-opacity": 0,
          "circle-stroke-color": color,
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0.4,
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-ring`,
        type: "circle",
        source,
        filter: unclustered,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            statusValue({ suspected: 6, confirmed: 7.5, monitoring: 6.5, localized: 5 }),
            10,
            statusValue({ suspected: 8, confirmed: 10, monitoring: 9, localized: 6.5 }),
          ],
          "circle-color": palette["map-background"],
          "circle-opacity": statusValue({ suspected: 0.35, confirmed: 0, monitoring: 0.25, localized: 0.2 }),
          "circle-stroke-color": color,
          "circle-stroke-width": ["case", hover, 2, statusValue({ suspected: 1.5, confirmed: 1.1, monitoring: 1.3, localized: 1 })],
          "circle-stroke-opacity": statusValue({ suspected: 0.95, confirmed: 0.6, monitoring: 0.8, localized: 0.7 }),
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-core`,
        type: "circle",
        source,
        filter: unclustered,
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            statusValue({ suspected: 1.8, confirmed: 4, monitoring: 3, localized: 1.8 }),
            10,
            statusValue({ suspected: 2.4, confirmed: 5.5, monitoring: 4.2, localized: 2.4 }),
          ],
          "circle-color": color,
          "circle-opacity": statusValue({ suspected: 1, confirmed: 1, monitoring: 0.75, localized: 0.9 }),
          "circle-stroke-color": palette["map-background"],
          "circle-stroke-width": ["case", ["==", ["get", "status"], "confirmed"], 1, 0],
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-selected`,
        type: "circle",
        source,
        filter: ["==", ["get", "id"], ""],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 16, 10, 21],
          "circle-opacity": 0,
          "circle-stroke-color": palette.text,
          "circle-stroke-width": 1.5,
          "circle-stroke-opacity": 0.9,
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-label`,
        type: "symbol",
        source,
        minzoom: 4.6,
        filter: unclustered,
        layout: {
          "text-field": ["format", ["get", "id"], {}, "  ", {}, ["to-string", ["get", "priority"]], { "font-scale": 0.92 }],
          "text-font": FONT_BOLD,
          "text-size": 10.5,
          "text-anchor": "left",
          "text-offset": [1.45, 0],
          "text-letter-spacing": 0.02,
          "text-optional": true,
        },
        paint: {
          "text-color": palette.text,
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.4,
        },
      },
    },
  ];
}

export const incidentsModule: LayerModule = {
  sources: {
    [INCIDENTS_SOURCE]: {
      type: "geojson",
      data: emptyCollection(),
      cluster: true,
      clusterRadius: 46,
      clusterMaxZoom: 5,
      clusterProperties: { maxPriority: ["max", ["get", "priority"]] },
      promoteId: "id",
    },
    [INCIDENTS_PRIORITY_SOURCE]: { type: "geojson", data: emptyCollection(), promoteId: "id" },
  },
  layers: (palette) => [
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: INCIDENT_CLUSTER_LAYER,
        type: "circle",
        source: INCIDENTS_SOURCE,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": palette.surface,
          "circle-opacity": 0.92,
          "circle-radius": ["step", ["get", "point_count"], 12, 3, 14.5, 6, 17],
          "circle-stroke-width": 1.5,
          "circle-stroke-color": [
            "step",
            ["get", "maxPriority"],
            palette["incident-low"],
            40,
            palette["incident-medium"],
            65,
            palette["incident-high"],
            85,
            palette["incident-critical"],
          ],
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${INCIDENTS_SOURCE}-cluster-count`,
        type: "symbol",
        source: INCIDENTS_SOURCE,
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": FONT_BOLD,
          "text-size": 11,
          "text-allow-overlap": true,
        },
        paint: { "text-color": palette.text },
      },
    },
    ...markerLayers(INCIDENTS_SOURCE, palette),
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: INCIDENT_PULSE_LAYER,
        type: "circle",
        source: INCIDENTS_PRIORITY_SOURCE,
        filter: ["all", ["==", ["get", "severity"], "critical"], ["!=", ["get", "status"], "localized"]],
        paint: {
          "circle-radius": 12,
          "circle-opacity": 0,
          "circle-stroke-color": palette["incident-critical"],
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0,
        },
      },
    },
    ...markerLayers(INCIDENTS_PRIORITY_SOURCE, palette),
  ],
};

export const INCIDENT_INTERACTIVE_LAYERS = [INCIDENTS_SOURCE, INCIDENTS_PRIORITY_SOURCE].flatMap((source) => [
  `${source}-core`,
  `${source}-ring`,
  `${source}-halo`,
]);
