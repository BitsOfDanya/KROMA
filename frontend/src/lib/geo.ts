import type { BBox, Position } from "./api/types";

export function snapBBox(bbox: BBox, cell = 10): BBox {
  const minLon = Math.max(-180, Math.floor(bbox[0] / cell) * cell - cell);
  const minLat = Math.max(-85, Math.floor(bbox[1] / cell) * cell - cell);
  const maxLon = Math.min(180, Math.ceil(bbox[2] / cell) * cell + cell);
  const maxLat = Math.min(85, Math.ceil(bbox[3] / cell) * cell + cell);
  return [minLon, minLat, maxLon, maxLat];
}

export function unionBBox(boxes: BBox[]): BBox | null {
  if (boxes.length === 0) return null;
  return boxes.reduce<BBox>(
    (acc, box) => [Math.min(acc[0], box[0]), Math.min(acc[1], box[1]), Math.max(acc[2], box[2]), Math.max(acc[3], box[3])],
    [...boxes[0]] as BBox,
  );
}

export function haversineKm(a: Position, b: Position): number {
  const radius = 6371.0088;
  const toRad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toRad;
  const dLon = (b[0] - a[0]) * toRad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * toRad) * Math.cos(b[1] * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function pathLengthKm(points: Position[]): number {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) total += haversineKm(points[index - 1], points[index]);
  return total;
}

export function parseNumber(value: string | null, min: number, max: number): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) return null;
  return parsed;
}
