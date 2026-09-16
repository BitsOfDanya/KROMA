export const PALETTE_TOKENS = [
  "background",
  "surface",
  "text",
  "text-secondary",
  "text-tertiary",
  "incident-critical",
  "incident-high",
  "incident-medium",
  "incident-low",
  "incident-localized",
  "confirmed",
  "observation",
  "observation-fresh",
  "burn-scar",
  "burn-low",
  "burn-moderate",
  "burn-high",
  "forecast-50",
  "forecast-80",
  "forecast-95",
  "infrastructure",
  "thermal-source",
  "protected-area",
  "cloud",
  "wind",
  "map-background",
  "map-land",
  "map-forest",
  "map-water",
  "map-river",
  "map-boundary",
  "map-country",
  "map-road-major",
  "map-road-minor",
  "map-rail",
  "map-residential",
  "map-label",
  "map-label-muted",
  "map-label-halo",
  "map-hillshade-shadow",
  "map-hillshade-highlight",
  "map-hillshade-accent",
] as const;

export type PaletteToken = (typeof PALETTE_TOKENS)[number];
export type Palette = Record<PaletteToken, string>;

export function readPalette(element: HTMLElement = document.documentElement): Palette {
  const styles = getComputedStyle(element);
  return Object.fromEntries(
    PALETTE_TOKENS.map((token) => [token, styles.getPropertyValue(`--${token}`).trim() || "#888888"]),
  ) as Palette;
}
