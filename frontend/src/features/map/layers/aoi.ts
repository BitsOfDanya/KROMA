import { FONT_REGULAR } from "../basemap";
import { emptyCollection, type LayerModule } from "./types";

export const AOI_SOURCE = "k-aoi";

export const aoiModule: LayerModule = {
  sources: {
    [AOI_SOURCE]: { type: "geojson", data: emptyCollection() },
  },
  layers: (palette) => [
    {
      placement: "under-labels",
      visible: (context) => context.layers.monitoringAoi,
      spec: {
        id: `${AOI_SOURCE}-fill`,
        type: "fill",
        source: AOI_SOURCE,
        filter: ["==", ["get", "feature_id"], "aoi"],
        paint: {
          "fill-color": palette["protected-area"],
          "fill-opacity": 0.08,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.monitoringAoi,
      spec: {
        id: `${AOI_SOURCE}-line`,
        type: "line",
        source: AOI_SOURCE,
        filter: ["==", ["get", "feature_id"], "aoi"],
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": palette["protected-area"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1.4, 8, 2.6],
          "line-opacity": 0.9,
        },
      },
    },
    {
      placement: "under-labels",
      visible: (context) => context.layers.monitoringAoi,
      spec: {
        id: `${AOI_SOURCE}-utm`,
        type: "line",
        source: AOI_SOURCE,
        filter: ["in", ["get", "feature_id"], ["literal", ["utm_32637", "utm_32638"]]],
        paint: {
          "line-color": palette["map-boundary"],
          "line-width": 1,
          "line-dasharray": [2, 2],
          "line-opacity": 0.45,
        },
      },
    },
    {
      placement: "over-labels",
      visible: (context) => context.layers.monitoringAoi,
      spec: {
        id: `${AOI_SOURCE}-label`,
        type: "symbol",
        source: AOI_SOURCE,
        filter: ["==", ["get", "feature_id"], "aoi"],
        layout: {
          "text-field": ["get", "name"],
          "text-font": FONT_REGULAR,
          "text-size": 12,
          "text-anchor": "center",
          "symbol-placement": "point",
        },
        paint: {
          "text-color": palette["protected-area"],
          "text-halo-color": palette["map-label-halo"],
          "text-halo-width": 1.4,
        },
      },
    },
  ],
};
