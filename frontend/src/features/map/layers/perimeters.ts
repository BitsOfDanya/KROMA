import type { ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";

import { emptyCollection, severityColor, TIME, type LayerModule, type VisibilityContext } from "./types";

export const PERIMETERS_SOURCE = "k-perimeters";

const current: ExpressionSpecification = ["all", ["<=", ["get", "valid_from"], TIME], [">", ["get", "valid_to"], TIME]];
const eventsOnly = (context: VisibilityContext) => context.evidenceMode === "events" && context.layers.incidents;

export const perimetersModule: LayerModule = {
  sources: { [PERIMETERS_SOURCE]: { type: "geojson", data: emptyCollection() } },
  layers: (palette) => {
    const color: ExpressionSpecification = [
      "case",
      ["==", ["get", "status"], "localized"],
      palette["incident-localized"],
      severityColor(palette),
    ];
    return [
      {
        placement: "under-labels",
        visible: (context) => eventsOnly(context) && context.layers.perimeter,
        spec: {
          id: `${PERIMETERS_SOURCE}-fill`,
          type: "fill",
          source: PERIMETERS_SOURCE,
          minzoom: 6,
          filter: ["all", ["==", ["get", "kind"], "perimeter"], current],
          paint: {
            "fill-color": color,
            "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.2, 11, 0.13],
          },
        },
      },
      {
        placement: "under-labels",
        visible: (context) => eventsOnly(context) && context.layers.perimeter,
        spec: {
          id: `${PERIMETERS_SOURCE}-line`,
          type: "line",
          source: PERIMETERS_SOURCE,
          minzoom: 6,
          filter: ["all", ["==", ["get", "kind"], "perimeter"], current],
          layout: { "line-join": "round" },
          paint: { "line-color": color, "line-width": 1, "line-opacity": 0.75 },
        },
      },
      {
        placement: "under-labels",
        visible: (context) => eventsOnly(context) && context.layers.activeFront,
        spec: {
          id: `${PERIMETERS_SOURCE}-front-glow`,
          type: "line",
          source: PERIMETERS_SOURCE,
          minzoom: 7,
          filter: ["all", ["==", ["get", "kind"], "front"], current],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": color, "line-width": 8, "line-blur": 6, "line-opacity": 0.4 },
        },
      },
      {
        placement: "under-labels",
        visible: (context) => eventsOnly(context) && context.layers.activeFront,
        spec: {
          id: `${PERIMETERS_SOURCE}-front`,
          type: "line",
          source: PERIMETERS_SOURCE,
          minzoom: 6.5,
          filter: ["all", ["==", ["get", "kind"], "front"], current],
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": color,
            "line-width": ["interpolate", ["linear"], ["zoom"], 7, 1.6, 12, 3.2],
          },
        },
      },
    ];
  },
};
