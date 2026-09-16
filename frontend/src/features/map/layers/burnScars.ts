import { FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const BURN_SCARS_SOURCE = "k-burn-scars";
export const BURN_SCAR_FILL_LAYER = `${BURN_SCARS_SOURCE}-fill`;

export const burnScarsModule: LayerModule = {
  sources: { [BURN_SCARS_SOURCE]: { type: "geojson", data: emptyCollection() } },
  layers: (palette) => [
    {
      placement: "under-labels",
      visible: (context) => context.layers.burnScars,
      spec: {
        id: BURN_SCAR_FILL_LAYER,
        type: "fill",
        source: BURN_SCARS_SOURCE,
        filter: ["==", ["get", "kind"], "scar"],
        paint: {
          "fill-color": palette["burn-scar"],
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.55, 8, 0.22, 10, 0.08],
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.burnScars,
      spec: {
        id: `${BURN_SCARS_SOURCE}-zones`,
        type: "fill",
        source: BURN_SCARS_SOURCE,
        minzoom: 8,
        filter: ["==", ["get", "kind"], "zone"],
        paint: {
          "fill-color": [
            "match",
            ["get", "severity"],
            "high",
            palette["burn-high"],
            "moderate",
            palette["burn-moderate"],
            palette["burn-low"],
          ],
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0, 9.5, 0.3],
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.burnScars,
      spec: {
        id: `${BURN_SCARS_SOURCE}-line`,
        type: "line",
        source: BURN_SCARS_SOURCE,
        minzoom: 5,
        filter: ["==", ["get", "kind"], "scar"],
        paint: { "line-color": palette["burn-scar"], "line-width": 1, "line-opacity": 0.85 },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.burnScars,
      spec: {
        id: `${BURN_SCARS_SOURCE}-label`,
        type: "symbol",
        source: BURN_SCARS_SOURCE,
        minzoom: 8,
        filter: ["==", ["get", "kind"], "scar"],
        layout: {
          "text-field": ["concat", "Гарь · ", ["to-string", ["round", ["get", "area_ha"]]], " га"],
          "text-font": FONT_REGULAR,
          "text-size": 10.5,
          "text-optional": true,
        },
        paint: { "text-color": palette["burn-scar"], "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.2 },
      },
    },
  ],
};
