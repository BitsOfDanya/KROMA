import { FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const THERMAL_SOURCE = "k-thermal";
export const THERMAL_LAYER = `${THERMAL_SOURCE}-icon`;

export const thermalModule: LayerModule = {
  sources: { [THERMAL_SOURCE]: { type: "geojson", data: emptyCollection() } },
  layers: (palette) => [
    {
      placement: "over-labels",
      visible: (context) => context.layers.thermalMemory,
      spec: {
        id: `${THERMAL_SOURCE}-ring`,
        type: "circle",
        source: THERMAL_SOURCE,
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 8, 10, 13],
          "circle-opacity": 0,
          "circle-stroke-color": palette["thermal-source"],
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0.45,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.thermalMemory,
      spec: {
        id: THERMAL_LAYER,
        type: "symbol",
        source: THERMAL_SOURCE,
        layout: {
          "icon-image": "k-diamond",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.55, 10, 0.85],
          "icon-allow-overlap": true,
          "text-field": ["step", ["zoom"], "", 6.5, ["get", "name"]],
          "text-font": FONT_REGULAR,
          "text-size": 10.5,
          "text-anchor": "left",
          "text-offset": [1.3, 0],
          "text-optional": true,
        },
        paint: {
          "icon-color": palette["thermal-source"],
          "text-color": palette["thermal-source"],
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.2,
        },
      },
    },
  ],
};
