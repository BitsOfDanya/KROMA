import type { ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";

import { FONT_BOLD, FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const WIND_SOURCE = "k-wind";
export const CLOUDS_SOURCE = "k-clouds";

const speedWidth: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["get", "speed_ms"],
  2,
  1.2,
  6,
  2.1,
  10,
  2.8,
  14,
  3.4,
];

const speedOpacity: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["get", "speed_ms"],
  2,
  0.45,
  8,
  0.75,
  14,
  0.95,
];

export const environmentModule: LayerModule = {
  sources: {
    [WIND_SOURCE]: { type: "geojson", data: emptyCollection() },
    [CLOUDS_SOURCE]: { type: "geojson", data: emptyCollection() },
  },
  layers: (palette) => [
    {
      placement: "under-labels",
      visible: (context) => context.layers.clouds,
      spec: {
        id: `${CLOUDS_SOURCE}-fill`,
        type: "fill",
        source: CLOUDS_SOURCE,
        paint: {
          "fill-color": palette.cloud,
          "fill-opacity": ["*", ["/", ["get", "probability"], 100], 0.3],
          "fill-antialias": false,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.clouds,
      spec: {
        id: `${CLOUDS_SOURCE}-line`,
        type: "line",
        source: CLOUDS_SOURCE,
        paint: { "line-color": palette.cloud, "line-width": 1, "line-opacity": 0.5, "line-dasharray": [1, 2] },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.clouds,
      spec: {
        id: `${CLOUDS_SOURCE}-label`,
        type: "symbol",
        source: CLOUDS_SOURCE,
        minzoom: 4,
        layout: {
          "text-field": ["concat", "Облачность ", ["to-string", ["get", "probability"]], "%"],
          "text-font": FONT_REGULAR,
          "text-size": 10.5,
        },
        paint: { "text-color": palette.cloud, "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.2 },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.wind,
      spec: {
        id: `${WIND_SOURCE}-glow`,
        type: "circle",
        source: WIND_SOURCE,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "speed_ms"], 2, 10, 12, 16],
          "circle-color": palette.wind,
          "circle-opacity": 0.12,
          "circle-blur": 0.7,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.wind,
      spec: {
        id: `${WIND_SOURCE}-shaft`,
        type: "line",
        source: WIND_SOURCE,
        filter: ["==", ["geometry-type"], "LineString"],
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": palette.wind,
          "line-width": speedWidth,
          "line-opacity": speedOpacity,
          "line-blur": 0.15,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.wind,
      spec: {
        id: `${WIND_SOURCE}-shaft-core`,
        type: "line",
        source: WIND_SOURCE,
        filter: ["==", ["geometry-type"], "LineString"],
        layout: {
          "line-cap": "round",
          "line-join": "round",
        },
        paint: {
          "line-color": palette.text,
          "line-width": ["-", speedWidth, 1.1],
          "line-opacity": 0.22,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.wind,
      spec: {
        id: `${WIND_SOURCE}-arrow`,
        type: "symbol",
        source: WIND_SOURCE,
        filter: ["==", ["geometry-type"], "Point"],
        layout: {
          "icon-image": "k-wind",
          "icon-rotate": ["get", "to_deg"],
          "icon-rotation-alignment": "map",
          "icon-pitch-alignment": "map",
          "icon-size": ["interpolate", ["linear"], ["get", "speed_ms"], 2, 0.55, 8, 0.78, 14, 1],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          "icon-anchor": "center",
          "text-field": [
            "step",
            ["zoom"],
            ["get", "compass"],
            5.2,
            ["concat", ["get", "compass"], " · ", ["to-string", ["get", "speed_ms"]], " м/с"],
          ],
          "text-font": FONT_BOLD,
          "text-size": ["interpolate", ["linear"], ["zoom"], 4, 10, 8, 11.5],
          "text-offset": [0, 1.55],
          "text-anchor": "top",
          "text-optional": true,
          "text-allow-overlap": false,
        },
        paint: {
          "icon-color": palette.wind,
          "icon-opacity": ["interpolate", ["linear"], ["get", "speed_ms"], 2, 0.7, 10, 1],
          "icon-halo-color": palette["map-label-halo"],
          "icon-halo-width": 1.4,
          "text-color": palette.wind,
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.4,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.wind,
      spec: {
        id: `${WIND_SOURCE}-caption`,
        type: "symbol",
        source: WIND_SOURCE,
        filter: ["all", ["==", ["geometry-type"], "Point"], ["==", ["get", "sample_index"], 0]],
        minzoom: 3,
        maxzoom: 5.5,
        layout: {
          "text-field": "Ветер",
          "text-font": FONT_BOLD,
          "text-size": 11,
          "text-offset": [0, -2.2],
          "text-anchor": "bottom",
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": palette.wind,
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.5,
          "text-opacity": 0.9,
        },
      },
    },
  ],
};
