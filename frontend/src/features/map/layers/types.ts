import type { ExpressionSpecification, LayerSpecification, SourceSpecification } from "@maplibre/maplibre-gl-style-spec";

import type { EvidenceMode, LayerId } from "@/state/workspace";

import type { Palette } from "../palette";

export interface VisibilityContext {
  layers: Record<LayerId, boolean>;
  evidenceMode: EvidenceMode;
}

export interface OperationalLayer {
  spec: LayerSpecification;
  placement: "under-labels" | "over-labels";
  visible: (context: VisibilityContext) => boolean;
}

export interface LayerModule {
  sources: Record<string, SourceSpecification>;
  layers: (palette: Palette) => OperationalLayer[];
}

export const TIME: ExpressionSpecification = ["global-state", "time"];
export const OPEN_ENDED = 4_102_444_800;

export const emptyCollection = () => ({ type: "FeatureCollection" as const, features: [] });

export function severityColor(palette: Palette, property = "severity"): ExpressionSpecification {
  return [
    "match",
    ["get", property],
    "critical",
    palette["incident-critical"],
    "high",
    palette["incident-high"],
    "medium",
    palette["incident-medium"],
    palette["incident-low"],
  ];
}

export const always = () => true;
