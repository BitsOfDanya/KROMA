import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";

import { LABEL_LAYER_PREFIX } from "../basemap";
import type { Palette } from "../palette";
import { aoiModule } from "./aoi";
import { burnScarsModule } from "./burnScars";
import { environmentModule } from "./environment";
import { forecastModule } from "./forecast";
import { hotspotsModule } from "./hotspots";
import { incidentsModule } from "./incidents";
import { measureModule } from "./measure";
import { perimetersModule } from "./perimeters";
import { riskObjectsModule } from "./riskObjects";
import { thermalModule } from "./thermal";
import type { OperationalLayer, VisibilityContext } from "./types";

const MODULES = [
  aoiModule,
  environmentModule,
  riskObjectsModule,
  burnScarsModule,
  forecastModule,
  perimetersModule,
  thermalModule,
  hotspotsModule,
  incidentsModule,
  measureModule,
];

export class OperationalLayers {
  private data = new Map<string, GeoJSON.GeoJSON>();
  private layers: OperationalLayer[] = [];

  install(map: MapLibreMap, palette: Palette, context: VisibilityContext) {
    const firstLabel = map.getStyle().layers.find((layer) => layer.id.startsWith(LABEL_LAYER_PREFIX))?.id;
    for (const layerModule of MODULES) {
      for (const [id, source] of Object.entries(layerModule.sources)) {
        if (map.getSource(id)) continue;
        const stored = this.data.get(id);
        map.addSource(id, stored && source.type === "geojson" ? { ...source, data: stored } : source);
      }
    }
    this.layers = MODULES.flatMap((layerModule) => layerModule.layers(palette));
    for (const layer of this.layers) {
      if (map.getLayer(layer.spec.id)) continue;
      map.addLayer(layer.spec, layer.placement === "under-labels" ? firstLabel : undefined);
    }
    this.applyVisibility(map, context);
  }

  applyVisibility(map: MapLibreMap, context: VisibilityContext) {
    for (const layer of this.layers) {
      if (!map.getLayer(layer.spec.id)) continue;
      const next = layer.visible(context) ? "visible" : "none";
      if (map.getLayoutProperty(layer.spec.id, "visibility") !== next) {
        map.setLayoutProperty(layer.spec.id, "visibility", next);
      }
    }
  }

  setData(map: MapLibreMap | null, sourceId: string, data: GeoJSON.GeoJSON) {
    this.data.set(sourceId, data);
    const source = map?.getSource(sourceId) as GeoJSONSource | undefined;
    if (source) void source.setData(data);
  }
}
