import type { ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";

import type { LayerId } from "@/state/workspace";

import { FONT_BOLD } from "../basemap";
import type { Palette } from "../palette";
import { emptyCollection, TIME, type LayerModule, type OperationalLayer } from "./types";

export const FORECAST_SOURCE = "k-forecast";

const LEVELS = [
  { level: "p95", token: "forecast-95", layer: "forecastP95", fill: 0.07, line: 0.55, dash: [2, 2] },
  { level: "p80", token: "forecast-80", layer: "forecastP80", fill: 0.11, line: 0.55, dash: [5, 2.5] },
  { level: "p50", token: "forecast-50", layer: "forecastP50", fill: 0.18, line: 0.75, dash: null },
] as const;

function levelLayers(palette: Palette, config: (typeof LEVELS)[number]): OperationalLayer[] {
  const filter: ExpressionSpecification = ["all", ["==", ["get", "level"], config.level], ["<=", ["get", "valid_from"], TIME]];
  const visible = (context: Parameters<OperationalLayer["visible"]>[0]) =>
    context.evidenceMode === "events" && context.layers[config.layer as LayerId];
  const color = palette[config.token];
  return [
    {
      placement: "under-labels",
      visible,
      spec: {
        id: `${FORECAST_SOURCE}-${config.level}-fill`,
        type: "fill",
        source: FORECAST_SOURCE,
        filter,
        paint: { "fill-color": color, "fill-opacity": config.fill, "fill-antialias": false },
      },
    },
    {
      placement: "under-labels",
      visible,
      spec: {
        id: `${FORECAST_SOURCE}-${config.level}-line`,
        type: "line",
        source: FORECAST_SOURCE,
        filter,
        layout: { "line-join": "round" },
        paint: {
          "line-color": color,
          "line-width": config.level === "p50" ? 1.2 : 1,
          "line-opacity": config.line,
          ...(config.dash ? { "line-dasharray": [...config.dash] } : {}),
        },
      },
    },
    {
      placement: "over-labels",
      visible,
      spec: {
        id: `${FORECAST_SOURCE}-${config.level}-label`,
        type: "symbol",
        source: FORECAST_SOURCE,
        minzoom: 9,
        filter,
        layout: {
          "symbol-placement": "line",
          "text-field": ["concat", ["upcase", ["get", "level"]], " · ", ["to-string", ["get", "horizon_hours"]], " ч"],
          "text-font": FONT_BOLD,
          "text-size": 9.5,
          "text-letter-spacing": 0.06,
          "symbol-spacing": 320,
        },
        paint: { "text-color": color, "text-halo-color": palette["map-label-halo"], "text-halo-width": 1.2 },
      },
    },
  ];
}

export const forecastModule: LayerModule = {
  sources: { [FORECAST_SOURCE]: { type: "geojson", data: emptyCollection() } },
  layers: (palette) => LEVELS.flatMap((config) => levelLayers(palette, config)),
};
