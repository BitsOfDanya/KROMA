export interface RasterProvider {
  tiles: string[];
  tileSize: number;
  maxzoom: number;
  attribution: string;
}

export interface MapProviderConfig {
  vectorTiles: string;
  glyphs: string;
  vectorAttribution: string;
  satellite: RasterProvider;
  terrainDem: RasterProvider & { encoding: "terrarium" | "mapbox" };
  comparisonBefore: RasterProvider;
}

const env = (value: string | undefined, fallback: string) => (value && value.trim() ? value.trim() : fallback);

export const mapProviders: MapProviderConfig = {
  vectorTiles: env(process.env.NEXT_PUBLIC_MAP_VECTOR_TILES_URL, "https://tiles.openfreemap.org/planet"),
  glyphs: env(process.env.NEXT_PUBLIC_MAP_GLYPHS_URL, "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf"),
  vectorAttribution: env(
    process.env.NEXT_PUBLIC_MAP_VECTOR_ATTRIBUTION,
    '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>',
  ),
  satellite: {
    tiles: [
      env(
        process.env.NEXT_PUBLIC_MAP_SATELLITE_TILES_URL,
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ),
    ],
    tileSize: 256,
    maxzoom: 18,
    attribution: env(process.env.NEXT_PUBLIC_MAP_SATELLITE_ATTRIBUTION, "Imagery © Esri, Maxar, Earthstar Geographics"),
  },
  terrainDem: {
    tiles: [
      env(
        process.env.NEXT_PUBLIC_MAP_TERRAIN_DEM_URL,
        "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
      ),
    ],
    tileSize: 256,
    maxzoom: 14,
    encoding: process.env.NEXT_PUBLIC_MAP_TERRAIN_DEM_ENCODING === "mapbox" ? "mapbox" : "terrarium",
    attribution: env(process.env.NEXT_PUBLIC_MAP_TERRAIN_ATTRIBUTION, "Terrain Tiles © Mapzen, AWS Open Data"),
  },
  comparisonBefore: {
    tiles: [
      env(
        process.env.NEXT_PUBLIC_MAP_SENTINEL_TILES_URL,
        "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg",
      ),
    ],
    tileSize: 256,
    maxzoom: 15,
    attribution: env(
      process.env.NEXT_PUBLIC_MAP_SENTINEL_ATTRIBUTION,
      'Sentinel-2 cloudless 2021 by <a href="https://s2maps.eu" target="_blank" rel="noreferrer">EOX IT Services GmbH</a> (contains modified Copernicus Sentinel data 2021)',
    ),
  },
};

export const INITIAL_VIEW = {
  center: [43.15, 48.65] as [number, number],
  zoom: 5.15,
};

