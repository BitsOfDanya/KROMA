import { FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const WIND_SOURCE = "k-wind";
export const CLOUDS_SOURCE = "k-clouds";

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
      placement: "over-labels",
      visible: (context) => context.layers.wind,
      spec: {
        id: `${WIND_SOURCE}-arrow`,
        type: "symbol",
        source: WIND_SOURCE,
        layout: {
          "icon-image": "k-arrow",
          "icon-rotate": ["get", "to_deg"],
          "icon-rotation-alignment": "map",
          "icon-size": ["interpolate", ["linear"], ["get", "speed_ms"], 2, 0.45, 12, 0.9],
          "icon-allow-overlap": true,
          "text-field": ["step", ["zoom"], "", 6, ["concat", ["to-string", ["get", "speed_ms"]], " м/с"]],
          "text-font": FONT_REGULAR,
          "text-size": 9.5,
          "text-offset": [0, 1.4],
          "text-optional": true,
        },
        paint: {
          "icon-color": palette.wind,
          "icon-opacity": 0.75,
          "text-color": palette.wind,
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1,
        },
      },
    },
  ],
};
