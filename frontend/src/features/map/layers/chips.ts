import { FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const CHIPS_SOURCE = "k-chips";
export const CHIPS_POINTS_SOURCE = "k-chip-points";
export const CHIPS_CLUSTER_LAYER = "k-chip-clusters";
export const CHIPS_FILL_LAYER = `${CHIPS_SOURCE}-fill`;
export const CHIPS_LINE_LAYER = `${CHIPS_SOURCE}-line`;
export const CHIPS_INTERACTIVE_LAYERS = [
  CHIPS_FILL_LAYER,
  CHIPS_LINE_LAYER,
  "k-chip-point",
];

export const chipsModule: LayerModule = {
  sources: {
    "k-chip-validation": { type: "geojson", data: emptyCollection() },
    [CHIPS_SOURCE]: { type: "geojson", data: emptyCollection() },
    [CHIPS_POINTS_SOURCE]: {
      type: "geojson",
      data: emptyCollection(),
      cluster: true,
      clusterMaxZoom: 8,
      clusterRadius: 45,
      clusterProperties: {
        af_count: ["+", ["case", ["==", ["get", "kind"], "af"], 1, 0]],
        bs_count: ["+", ["case", ["==", ["get", "kind"], "bs"], 1, 0]],
      },
    },
  },
  layers: (palette) => [
    {
      placement: "over-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: "k-chip-validation-fill",
        type: "fill",
        source: "k-chip-validation",
        minzoom: 8,
        paint: {
          "fill-color": [
            "match",
            ["get", "severity"],
            "low",
            "#e8b058",
            "moderate",
            "#e87840",
            "high",
            "#dc3830",
            "fp",
            "#dc3830",
            "fn",
            "#4884e8",
            "mismatch",
            "#f0be3c",
            "#42be78",
          ],
          "fill-opacity": 0.55,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: "k-chip-validation-points",
        type: "circle",
        source: "k-chip-validation",
        filter: ["==", ["geometry-type"], "Point"],
        minzoom: 8,
        paint: {
          "circle-color": palette["incident-critical"],
          "circle-radius": 3,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: CHIPS_CLUSTER_LAYER,
        type: "circle",
        source: CHIPS_POINTS_SOURCE,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": palette["burn-scar"],
          "circle-radius": [
            "step",
            ["get", "point_count"],
            16,
            20,
            21,
            100,
            26,
          ],
          "circle-opacity": 0.8,
          "circle-stroke-width": 1,
          "circle-stroke-color": palette.text,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: "k-chip-count",
        type: "symbol",
        source: CHIPS_POINTS_SOURCE,
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": FONT_REGULAR,
          "text-size": 12,
        },
        paint: { "text-color": palette.text },
      },
    },
    {
      placement: "over-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: "k-chip-point",
        type: "circle",
        source: CHIPS_POINTS_SOURCE,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "match",
            ["get", "kind"],
            "af",
            palette["incident-critical"],
            palette["burn-scar"],
          ],
          "circle-radius": 4,
          "circle-opacity": 0.85,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: CHIPS_FILL_LAYER,
        type: "fill",
        source: CHIPS_SOURCE,
        minzoom: 8,
        paint: {
          "fill-color": palette["burn-scar"],
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            0.16,
            0.025,
          ],
        },
      },
    },
    {
      placement: "under-labels",
      visible: (c) => c.layers.monitoringChips,
      spec: {
        id: CHIPS_LINE_LAYER,
        type: "line",
        source: CHIPS_SOURCE,
        minzoom: 8,
        paint: {
          "line-color": palette["burn-scar"],
          "line-width": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            2,
            0.6,
          ],
          "line-opacity": 0.35,
        },
      },
    },
  ],
};
