import { FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const CHIPS_SOURCE = "k-chips";
export const CHIPS_FILL_LAYER = `${CHIPS_SOURCE}-fill`;
export const CHIPS_LINE_LAYER = `${CHIPS_SOURCE}-line`;
export const CHIPS_INTERACTIVE_LAYERS = [CHIPS_FILL_LAYER, CHIPS_LINE_LAYER];

export const chipsModule: LayerModule = {
  sources: {
    [CHIPS_SOURCE]: { type: "geojson", data: emptyCollection() },
  },
  layers: (palette) => [
    {
      placement: "under-labels",
      visible: (context) => context.layers.monitoringChips,
      spec: {
        id: `${CHIPS_SOURCE}-fill`,
        type: "fill",
        source: CHIPS_SOURCE,
        paint: {
          "fill-color": [
            "match",
            ["get", "kind"],
            "af",
            palette["incident-critical"],
            "bs",
            palette["burn-scar"],
            palette["protected-area"],
          ],
          "fill-opacity": 0.22,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.monitoringChips,
      spec: {
        id: `${CHIPS_SOURCE}-line`,
        type: "line",
        source: CHIPS_SOURCE,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": [
            "match",
            ["get", "kind"],
            "af",
            palette["incident-critical"],
            "bs",
            palette["burn-scar"],
            palette["protected-area"],
          ],
          "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.8, 9, 1.6],
          "line-opacity": 0.85,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.monitoringChips,
      spec: {
        id: `${CHIPS_SOURCE}-label`,
        type: "symbol",
        source: CHIPS_SOURCE,
        minzoom: 8,
        layout: {
          "text-field": ["get", "chip_id"],
          "text-font": FONT_REGULAR,
          "text-size": 10,
          "text-optional": true,
        },
        paint: {
          "text-color": palette.text,
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.2,
        },
      },
    },
  ],
};
