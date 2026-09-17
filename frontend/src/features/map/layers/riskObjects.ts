import { FONT_BOLD, FONT_ITALIC, FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const RISK_SOURCE = "k-risk";
export const RISK_INTERACTIVE_LAYERS = [`${RISK_SOURCE}-settlement`, `${RISK_SOURCE}-infrastructure`, `${RISK_SOURCE}-line`, `${RISK_SOURCE}-power`];

export const riskObjectsModule: LayerModule = {
  sources: { [RISK_SOURCE]: { type: "geojson", data: emptyCollection() } },
  layers: (palette) => [
    {
      placement: "under-labels",
      visible: (context) => context.layers.protectedAreas,
      spec: {
        id: `${RISK_SOURCE}-protected-fill`,
        type: "fill",
        source: RISK_SOURCE,
        filter: ["==", ["get", "kind"], "protected_area"],
        paint: { "fill-color": palette["protected-area"], "fill-opacity": 0.07 },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.protectedAreas,
      spec: {
        id: `${RISK_SOURCE}-protected-line`,
        type: "line",
        source: RISK_SOURCE,
        filter: ["==", ["get", "kind"], "protected_area"],
        paint: { "line-color": palette["protected-area"], "line-width": 1, "line-opacity": 0.7, "line-dasharray": [3, 2] },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.protectedAreas,
      spec: {
        id: `${RISK_SOURCE}-protected-label`,
        type: "symbol",
        source: RISK_SOURCE,
        minzoom: 5,
        filter: ["==", ["get", "kind"], "protected_area"],
        layout: { "text-field": ["get", "name"], "text-font": FONT_ITALIC, "text-size": 10.5, "text-max-width": 10 },
        paint: { "text-color": palette["protected-area"], "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.2 },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.roads,
      spec: {
        id: `${RISK_SOURCE}-line`,
        type: "line",
        source: RISK_SOURCE,
        minzoom: 6,
        filter: ["==", ["get", "kind"], "road"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": palette.infrastructure,
          "line-width": ["interpolate", ["linear"], ["zoom"], 6, 1, 12, 2.4],
          "line-opacity": 0.8,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.infrastructure,
      spec: {
        id: `${RISK_SOURCE}-power`,
        type: "line",
        source: RISK_SOURCE,
        minzoom: 6,
        filter: ["==", ["get", "kind"], "power_line"],
        paint: {
          "line-color": palette.infrastructure,
          "line-width": ["interpolate", ["linear"], ["zoom"], 6, 1, 12, 1.8],
          "line-dasharray": [1.5, 1.5],
          "line-opacity": 0.9,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.roads || context.layers.infrastructure,
      spec: {
        id: `${RISK_SOURCE}-line-label`,
        type: "symbol",
        source: RISK_SOURCE,
        minzoom: 9,
        filter: ["match", ["get", "kind"], ["road", "power_line"], true, false],
        layout: {
          "symbol-placement": "line",
          "text-field": ["get", "name"],
          "text-font": FONT_REGULAR,
          "text-size": 10,
          "symbol-spacing": 420,
        },
        paint: { "text-color": palette.infrastructure, "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.2 },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.infrastructure,
      spec: {
        id: `${RISK_SOURCE}-infrastructure`,
        type: "symbol",
        source: RISK_SOURCE,
        minzoom: 6.5,
        filter: ["==", ["get", "kind"], "infrastructure"],
        layout: {
          "icon-image": "k-square",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 6.5, 0.5, 11, 0.8],
          "icon-allow-overlap": true,
          "text-field": ["step", ["zoom"], "", 9, ["get", "name"]],
          "text-font": FONT_REGULAR,
          "text-size": 10.5,
          "text-anchor": "left",
          "text-offset": [0.9, 0],
          "text-optional": true,
        },
        paint: {
          "icon-color": palette.infrastructure,
          "text-color": palette.infrastructure,
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.2,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.settlements,
      spec: {
        id: `${RISK_SOURCE}-settlement`,
        type: "circle",
        source: RISK_SOURCE,
        minzoom: 5.5,
        filter: ["==", ["get", "kind"], "settlement"],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 5.5, 2.5, 10, 4.5],
          "circle-color": palette["map-background"],
          "circle-stroke-color": palette.text,
          "circle-stroke-width": 1.4,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.settlements,
      spec: {
        id: `${RISK_SOURCE}-settlement-label`,
        type: "symbol",
        source: RISK_SOURCE,
        minzoom: 6,
        filter: ["==", ["get", "kind"], "settlement"],
        layout: {
          "text-field": ["get", "name"],
          "text-font": FONT_BOLD,
          "text-size": ["interpolate", ["linear"], ["zoom"], 6, 10.5, 11, 12.5],
          "text-anchor": "top",
          "text-offset": [0, 0.7],
        },
        paint: { "text-color": palette.text, "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.4 },
      },
    },
  ],
};
