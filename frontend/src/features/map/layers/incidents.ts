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

const activeFire: ExpressionSpecification = [
  "all",
  unclustered,
  ["in", ["get", "status"], ["literal", ["confirmed", "monitoring"]]],
];
const quietPoint: ExpressionSpecification = [
  "all",
  unclustered,
  ["!", ["in", ["get", "status"], ["literal", ["confirmed", "monitoring"]]]],
];

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
        filter: activeFire,
        paint: {
          "circle-color": color,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 9, 10, 15],
          "circle-opacity": ["case", ["==", ["get", "severity"], "critical"], 0.22, 0.14],
          "circle-blur": 0.6,
          "circle-pitch-alignment": "map",
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
        filter: quietPoint,
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
          "circle-opacity": 0.35,
          "circle-stroke-color": color,
          "circle-stroke-width": ["case", hover, 2, 1.5],
          "circle-stroke-opacity": 0.95,
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
        filter: quietPoint,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.8, 10, 2.5],
          "circle-color": color,
          "circle-opacity": 1,
        },
      },
    },
    {
      placement: "over-labels",
      visible: visibleInEvents,
      spec: {
        id: `${source}-flame`,
        type: "symbol",
        source,
        filter: activeFire,
        layout: {
          "icon-image": "k-flame",
          "icon-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            ["case", ["==", ["get", "severity"], "critical"], 0.42, 0.34],
            10,
            ["case", ["==", ["get", "severity"], "critical"], 0.62, 0.5],
          ],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-anchor": "bottom",
          "icon-offset": [0, 2],
        },
        paint: {
          "icon-color": color,
          "icon-opacity": ["case", hover, 1, ["==", ["get", "status"], "monitoring"], 0.82, 0.95],
          "icon-halo-color": palette["map-background"],
          "icon-halo-width": 1.1,
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
          "text-offset": [1.55, -0.15],
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
  `${source}-flame`,
]);
