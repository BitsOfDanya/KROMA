import type { FeatureCollection, Position } from "@/lib/api/types";
import { compassPoint } from "@/lib/format";

type WindProps = {
  from_deg?: number;
  to_deg?: number;
  speed_ms?: number;
};

function destination(lon: number, lat: number, bearingDeg: number, distanceKm: number): Position {
  const rad = Math.PI / 180;
  const north = Math.cos(bearingDeg * rad) * distanceKm;
  const east = Math.sin(bearingDeg * rad) * distanceKm;
  const dLat = north / 111.32;
  const dLon = east / (111.32 * Math.max(0.2, Math.cos(lat * rad)));
  return [lon + dLon, lat + dLat];
}

/** Turns wind sample points into short flow vectors + labelled tips. */
export function enrichWindCollection(collection: FeatureCollection<WindProps> | undefined): GeoJSON.FeatureCollection {
  if (!collection) {
    return { type: "FeatureCollection", features: [] };
  }

  const features: GeoJSON.Feature[] = [];
  collection.features.forEach((feature, index) => {
    if (feature.geometry?.type !== "Point") return;
    const [lon, lat] = feature.geometry.coordinates as Position;
    const speed = Number(feature.properties?.speed_ms ?? 0);
    const toDeg = Number(feature.properties?.to_deg ?? ((Number(feature.properties?.from_deg ?? 0) + 180) % 360));
    const lengthKm = Math.min(28, Math.max(9, 7 + speed * 1.35));
    const tip = destination(lon, lat, toDeg, lengthKm);
    const mid = destination(lon, lat, toDeg, lengthKm * 0.55);
    const compass = compassPoint(toDeg);

    features.push({
      type: "Feature",
      id: `wind-shaft-${index}`,
      geometry: {
        type: "LineString",
        coordinates: [
          [lon, lat],
          mid,
          tip,
        ],
      },
      properties: {
        speed_ms: speed,
        to_deg: toDeg,
        compass,
      },
    });

    features.push({
      type: "Feature",
      id: `wind-tip-${index}`,
      geometry: { type: "Point", coordinates: tip },
      properties: {
        speed_ms: speed,
        to_deg: toDeg,
        compass,
        sample_index: index,
        label: `${compass} · ${speed} м/с`,
      },
    });
  });

  return { type: "FeatureCollection", features };
}
