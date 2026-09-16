import type { ExpressionSpecification, LayerSpecification, StyleSpecification } from "@maplibre/maplibre-gl-style-spec";

import { mapProviders } from "@/config/map";

import type { Palette } from "./palette";

export type BasemapMode = "map" | "satellite" | "terrain";
export type ThemeName = "dark" | "light";

export const FONT_REGULAR = ["Noto Sans Regular"];
export const FONT_BOLD = ["Noto Sans Bold"];
export const FONT_ITALIC = ["Noto Sans Italic"];

const NAME: ExpressionSpecification = ["coalesce", ["get", "name:ru"], ["get", "name:nonlatin"], ["get", "name"]];
const OMT = "openmaptiles";

const isPolygon: ExpressionSpecification = ["match", ["geometry-type"], ["Polygon", "MultiPolygon"], true, false];
const isLine: ExpressionSpecification = ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false];

function baseLayers(palette: Palette, mode: BasemapMode, theme: ThemeName): LayerSpecification[] {
  const layers: LayerSpecification[] = [
    { id: "bm-background", type: "background", paint: { "background-color": palette["map-background"] } },
  ];

  if (mode === "satellite") {
    layers.push({
      id: "bm-satellite",
      type: "raster",
      source: "satellite",
      paint: {
        "raster-fade-duration": 180,
        "raster-saturation": theme === "dark" ? -0.25 : -0.1,
        "raster-brightness-max": theme === "dark" ? 0.78 : 0.95,
        "raster-contrast": theme === "dark" ? 0.05 : 0,
      },
    });
    return layers;
  }

  layers.push({
    id: "bm-forest",
    type: "fill",
    source: OMT,
    "source-layer": "landcover",
    filter: ["all", isPolygon, ["==", ["get", "class"], "wood"]],
    paint: {
      "fill-color": palette["map-forest"],
      "fill-opacity": ["interpolate", ["linear"], ["zoom"], 3, mode === "terrain" ? 0.9 : 0.55, 10, mode === "terrain" ? 1 : 0.8],
      "fill-antialias": false,
    },
  });

  if (mode === "terrain") {
    layers.push({
      id: "bm-hillshade",
      type: "hillshade",
      source: "terrain-dem",
      paint: {
        "hillshade-shadow-color": palette["map-hillshade-shadow"],
        "hillshade-highlight-color": palette["map-hillshade-highlight"],
        "hillshade-accent-color": palette["map-hillshade-accent"],
        "hillshade-exaggeration": theme === "dark" ? 0.55 : 0.42,
        "hillshade-illumination-direction": 315,
      },
    });
  }

  layers.push(
    {
      id: "bm-residential",
      type: "fill",
      source: OMT,
      "source-layer": "landuse",
      minzoom: 8,
      filter: ["all", isPolygon, ["match", ["get", "class"], ["residential", "suburb", "neighbourhood"], true, false]],
      paint: { "fill-color": palette["map-residential"], "fill-opacity": 0.8 },
    },
    {
      id: "bm-water",
      type: "fill",
      source: OMT,
      "source-layer": "water",
      filter: ["all", isPolygon, ["!=", ["get", "brunnel"], "tunnel"]],
      paint: { "fill-color": palette["map-water"], "fill-antialias": true },
    },
  );
  return layers;
}

function lineLayers(palette: Palette, mode: BasemapMode): LayerSpecification[] {
  const satellite = mode === "satellite";
  const roadMajor = satellite ? "rgba(255,255,255,0.28)" : palette["map-road-major"];
  const roadMinor = satellite ? "rgba(255,255,255,0.16)" : palette["map-road-minor"];
  return [
    {
      id: "bm-river",
      type: "line",
      source: OMT,
      "source-layer": "waterway",
      filter: ["all", isLine, ["match", ["get", "class"], ["river"], true, false], ["!=", ["get", "brunnel"], "tunnel"]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": satellite ? "rgba(140,190,210,0.35)" : palette["map-river"],
        "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 3, 0.5, 8, 1.2, 13, 3],
      },
    },
    {
      id: "bm-stream",
      type: "line",
      source: OMT,
      "source-layer": "waterway",
      minzoom: 9,
      filter: ["all", isLine, ["match", ["get", "class"], ["canal", "stream"], true, false]],
      paint: {
        "line-color": satellite ? "rgba(140,190,210,0.25)" : palette["map-river"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.4, 14, 1.2],
        "line-opacity": 0.8,
      },
    },
    {
      id: "bm-road-minor",
      type: "line",
      source: OMT,
      "source-layer": "transportation",
      minzoom: 10,
      filter: ["all", isLine, ["match", ["get", "class"], ["minor", "service", "track"], true, false]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": roadMinor,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.4, 15, 2.5],
      },
    },
    {
      id: "bm-road-secondary",
      type: "line",
      source: OMT,
      "source-layer": "transportation",
      minzoom: 7,
      filter: ["all", isLine, ["match", ["get", "class"], ["secondary", "tertiary"], true, false]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": roadMajor,
        "line-width": ["interpolate", ["linear"], ["zoom"], 7, 0.4, 12, 1.6, 15, 4],
        "line-opacity": 0.85,
      },
    },
    {
      id: "bm-road-major",
      type: "line",
      source: OMT,
      "source-layer": "transportation",
      minzoom: 4.5,
      filter: ["all", isLine, ["match", ["get", "class"], ["motorway", "trunk", "primary"], true, false]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": roadMajor,
        "line-width": ["interpolate", ["linear"], ["zoom"], 4.5, 0.4, 8, 1.1, 12, 2.4, 15, 5],
      },
    },
    {
      id: "bm-rail",
      type: "line",
      source: OMT,
      "source-layer": "transportation",
      minzoom: 6,
      filter: ["all", isLine, ["==", ["get", "class"], "rail"], ["!", ["has", "service"]]],
      paint: {
        "line-color": satellite ? "rgba(255,255,255,0.2)" : palette["map-rail"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 12, 1.2],
        "line-dasharray": [3, 2],
      },
    },
    {
      id: "bm-boundary-region",
      type: "line",
      source: OMT,
      "source-layer": "boundary",
      minzoom: 2.5,
      filter: ["all", ["==", ["get", "admin_level"], 4], ["!=", ["get", "maritime"], 1]],
      layout: { "line-join": "round" },
      paint: {
        "line-color": satellite ? "rgba(255,255,255,0.35)" : palette["map-boundary"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.6, 8, 1.1],
        "line-dasharray": [4, 2.5],
      },
    },
    {
      id: "bm-boundary-country",
      type: "line",
      source: OMT,
      "source-layer": "boundary",
      filter: ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1], ["!=", ["get", "disputed"], 1]],
      layout: { "line-join": "round" },
      paint: {
        "line-color": satellite ? "rgba(255,255,255,0.55)" : palette["map-country"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.8, 8, 1.6],
      },
    },
  ];
}

export function labelLayers(palette: Palette, mode: BasemapMode): LayerSpecification[] {
  const satellite = mode === "satellite";
  const label = satellite ? "#f4f1ea" : palette["map-label"];
  const muted = satellite ? "rgba(244,241,234,0.75)" : palette["map-label-muted"];
  const halo = satellite ? "rgba(0,0,0,0.75)" : palette["map-label-halo"];
  return [
    {
      id: "bm-label-river",
      type: "symbol",
      source: OMT,
      "source-layer": "waterway",
      minzoom: 7,
      filter: ["all", isLine, ["==", ["get", "class"], "river"]],
      layout: {
        "symbol-placement": "line",
        "text-field": NAME,
        "text-font": FONT_ITALIC,
        "text-size": ["interpolate", ["linear"], ["zoom"], 7, 10, 12, 12],
        "symbol-spacing": 400,
        "text-letter-spacing": 0.05,
      },
      paint: { "text-color": satellite ? "rgba(190,220,235,0.9)" : palette["map-river"], "text-halo-color": halo, "text-halo-width": 1.2 },
    },
    {
      id: "bm-label-water",
      type: "symbol",
      source: OMT,
      "source-layer": "water_name",
      filter: ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
      layout: {
        "text-field": NAME,
        "text-font": FONT_ITALIC,
        "text-size": ["interpolate", ["linear"], ["zoom"], 3, 10, 10, 12],
        "text-max-width": 8,
        "text-letter-spacing": 0.08,
      },
      paint: { "text-color": muted, "text-halo-color": halo, "text-halo-width": 1 },
    },
    {
      id: "bm-label-village",
      type: "symbol",
      source: OMT,
      "source-layer": "place",
      minzoom: 9,
      filter: ["match", ["get", "class"], ["village", "hamlet"], true, false],
      layout: { "text-field": NAME, "text-font": FONT_REGULAR, "text-size": 10.5, "text-max-width": 8 },
      paint: { "text-color": muted, "text-halo-color": halo, "text-halo-width": 1.2 },
    },
    {
      id: "bm-label-town",
      type: "symbol",
      source: OMT,
      "source-layer": "place",
      minzoom: 6,
      filter: ["==", ["get", "class"], "town"],
      layout: {
        "text-field": NAME,
        "text-font": FONT_REGULAR,
        "text-size": ["interpolate", ["linear"], ["zoom"], 6, 10.5, 12, 13],
        "text-max-width": 8,
      },
      paint: { "text-color": label, "text-halo-color": halo, "text-halo-width": 1.2 },
    },
    {
      id: "bm-label-city",
      type: "symbol",
      source: OMT,
      "source-layer": "place",
      minzoom: 3.5,
      filter: ["==", ["get", "class"], "city"],
      layout: {
        "text-field": NAME,
        "text-font": FONT_REGULAR,
        "text-size": ["interpolate", ["linear"], ["zoom"], 4, 11, 8, 13.5, 12, 16],
        "text-max-width": 8,
      },
      paint: { "text-color": label, "text-halo-color": halo, "text-halo-width": 1.4 },
    },
    {
      id: "bm-label-state",
      type: "symbol",
      source: OMT,
      "source-layer": "place",
      minzoom: 3.2,
      maxzoom: 7.5,
      filter: ["==", ["get", "class"], "state"],
      layout: {
        "text-field": NAME,
        "text-font": FONT_REGULAR,
        "text-size": ["interpolate", ["linear"], ["zoom"], 3, 9.5, 7, 11],
        "text-transform": "uppercase",
        "text-letter-spacing": 0.14,
        "text-max-width": 9,
      },
      paint: { "text-color": muted, "text-halo-color": halo, "text-halo-width": 1 },
    },
    {
      id: "bm-label-country",
      type: "symbol",
      source: OMT,
      "source-layer": "place",
      maxzoom: 6,
      filter: ["==", ["get", "class"], "country"],
      layout: {
        "text-field": NAME,
        "text-font": FONT_BOLD,
        "text-size": ["interpolate", ["linear"], ["zoom"], 2, 10, 5, 13],
        "text-transform": "uppercase",
        "text-letter-spacing": 0.24,
        "text-max-width": 10,
      },
      paint: { "text-color": muted, "text-halo-color": halo, "text-halo-width": 1 },
    },
  ];
}

export function buildBasemapStyle(mode: BasemapMode, theme: ThemeName, palette: Palette): StyleSpecification {
  const sources: StyleSpecification["sources"] = {
    [OMT]: { type: "vector", url: mapProviders.vectorTiles, attribution: mapProviders.vectorAttribution },
  };
  if (mode === "satellite") {
    sources.satellite = { type: "raster", ...mapProviders.satellite };
  }
  if (mode === "terrain") {
    const { encoding, ...dem } = mapProviders.terrainDem;
    sources["terrain-dem"] = { type: "raster-dem", encoding, ...dem };
  }
  return {
    version: 8,
    name: `kroma-${mode}-${theme}`,
    glyphs: mapProviders.glyphs,
    state: {
      time: { default: 4_102_444_800 },
      freshWindow: { default: 21_600 },
    },
    sources,
    layers: [...baseLayers(palette, mode, theme), ...lineLayers(palette, mode), ...labelLayers(palette, mode)],
  };
}

export const LABEL_LAYER_PREFIX = "bm-label-";
