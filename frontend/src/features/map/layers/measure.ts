import { FONT_BOLD } from "../basemap";
import { always, emptyCollection, type LayerModule } from "./types";

export const MEASURE_SOURCE = "k-measure";

export const measureModule: LayerModule = {
  sources: { [MEASURE_SOURCE]: { type: "geojson", data: emptyCollection() } },
  layers: (palette) => [
    {
      placement: "over-labels",
      visible: always,
      spec: {
        id: `${MEASURE_SOURCE}-line`,
        type: "line",
        source: MEASURE_SOURCE,
        filter: ["==", ["geometry-type"], "LineString"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": palette.text, "line-width": 1.6, "line-dasharray": [2, 1.5] },
      },
    },
    {
      placement: "over-labels",
      visible: always,
      spec: {
        id: `${MEASURE_SOURCE}-point`,
        type: "circle",
        source: MEASURE_SOURCE,
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 3.5,
          "circle-color": palette["map-background"],
          "circle-stroke-color": palette.text,
          "circle-stroke-width": 1.5,
        },
      },
    },
    {
      placement: "over-labels",
      visible: always,
      spec: {
        id: `${MEASURE_SOURCE}-label`,
        type: "symbol",
        source: MEASURE_SOURCE,
        filter: ["all", ["==", ["geometry-type"], "Point"], ["has", "label"]],
        layout: {
          "text-field": ["get", "label"],
          "text-font": FONT_BOLD,
          "text-size": 11,
          "text-anchor": "left",
          "text-offset": [0.9, 0],
          "text-allow-overlap": true,
        },
        paint: { "text-color": palette.text, "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.5 },
      },
    },
  ],
};
