"use client";

import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type GeoJSONSource,
  type MapLayerMouseEvent,
} from "maplibre-gl";
import { Eye, EyeOff, Focus, MousePointer2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import "@/features/map/mapWorker";
import { buildBasemapStyle } from "@/features/map/basemap";
import { readPalette } from "@/features/map/palette";
import type { AnalysisResult, BBox } from "@/lib/api/types";
import { formatArea, formatExact } from "@/lib/format";
import { useTheme } from "@/state/theme";

import styles from "./analysis.module.css";

interface AnalysisMapProps {
  result: AnalysisResult | null;
  draftBBox: BBox | null;
  onDraftBBox: (bbox: BBox) => void;
}

function rectangle(bbox: BBox, state: "draft" | "applied"): GeoJSON.Feature {
  const [west, south, east, north] = bbox;
  return {
    type: "Feature",
    properties: { state },
    geometry: {
      type: "Polygon",
      coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    },
  };
}

const emptyCollection = (): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features: [] });

const severityLabels: Record<string, string> = {
  low: "Слабая степень поражения",
  moderate: "Средняя степень поражения",
  high: "Сильная степень поражения",
};

export function AnalysisMap({ result, draftBBox, onDraftBBox }: AnalysisMapProps) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const popupRef = useRef<Popup | null>(null);
  const onDraftRef = useRef(onDraftBBox);
  const initialBoundsRef = useRef<BBox>(result?.request.bbox ?? draftBBox ?? [92, 54, 106, 62]);
  const [loaded, setLoaded] = useState(false);
  const [basemapError, setBasemapError] = useState(false);
  const [zonesVisible, setZonesVisible] = useState(true);
  const [hotspotsVisible, setHotspotsVisible] = useState(true);

  useEffect(() => {
    onDraftRef.current = onDraftBBox;
  }, [onDraftBBox]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setLoaded(false);
    setBasemapError(false);
    const initial = initialBoundsRef.current;
    const map = new MapLibreMap({
      container,
      style: buildBasemapStyle("map", theme, readPalette()),
      bounds: [[initial[0], initial[1]], [initial[2], initial[3]]],
      fitBoundsOptions: { padding: 48, maxZoom: 11 },
      attributionControl: { compact: true },
    });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("error", () => setBasemapError(true));
    map.on("load", () => {
      map.addSource("analysis-zones", { type: "geojson", data: emptyCollection() });
      map.addSource("analysis-hotspots", { type: "geojson", data: emptyCollection() });
      map.addSource("analysis-aoi", { type: "geojson", data: emptyCollection() });
      ([1, 2, 3] as const).forEach((classId) => {
        const colors = { 1: "#c99a67", 2: "#b05a36", 3: "#7b2624" };
        map.addLayer({
          id: `analysis-zone-${classId}`,
          type: "fill",
          source: "analysis-zones",
          filter: ["==", ["get", "class_id"], classId],
          paint: {
            "fill-color": colors[classId],
            "fill-opacity": 0.62,
            "fill-outline-color": theme === "dark" ? "#f4f1ea" : "#4b241f",
          },
        });
      });
      map.addLayer({
        id: "analysis-hotspot",
        type: "circle",
        source: "analysis-hotspots",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 4, 12, 8],
          "circle-color": "#ff784e",
          "circle-stroke-color": theme === "dark" ? "#fff7e8" : "#5e150c",
          "circle-stroke-width": 1.5,
        },
      });
      map.addLayer({
        id: "analysis-aoi-applied",
        type: "line",
        source: "analysis-aoi",
        filter: ["==", ["get", "state"], "applied"],
        paint: {
          "line-color": "#396aff",
          "line-width": 3,
        },
      });
      map.addLayer({
        id: "analysis-aoi-draft",
        type: "line",
        source: "analysis-aoi",
        filter: ["==", ["get", "state"], "draft"],
        paint: {
          "line-color": "#16b99e",
          "line-width": 2,
          "line-dasharray": [2, 2],
        },
      });

      const zoneClick = (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const properties = feature.properties ?? {};
        const node = document.createElement("div");
        node.className = styles.mapPopup;
        const title = document.createElement("strong");
        const severity = String(properties.severity ?? "");
        title.textContent = severityLabels[severity] ?? "Зона поражения";
        const detail = document.createElement("span");
        detail.textContent = `${String(properties.burn_event_id ?? "—")} · ${formatArea(Number(properties.area_ha ?? 0))}`;
        const date = document.createElement("span");
        date.textContent = `Послепожарная съёмка: ${formatExact(String(properties.after_acquired_at ?? ""))}`;
        node.append(title, detail, date);
        popupRef.current?.remove();
        popupRef.current = new Popup({ closeButton: true, maxWidth: "300px" })
          .setLngLat(event.lngLat)
          .setDOMContent(node)
          .addTo(map);
      };
      const hotspotClick = (event: MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const properties = feature.properties ?? {};
        const node = document.createElement("div");
        node.className = styles.mapPopup;
        const title = document.createElement("strong");
        title.textContent = String(properties.id ?? "Термоточка");
        const date = document.createElement("span");
        date.textContent = formatExact(String(properties.acquired_at ?? ""));
        const source = document.createElement("span");
        source.textContent = String(properties.source ?? "Источник не указан");
        node.append(title, date, source);
        popupRef.current?.remove();
        popupRef.current = new Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(event.lngLat)
          .setDOMContent(node)
          .addTo(map);
      };
      ([1, 2, 3] as const).forEach((classId) => map.on("click", `analysis-zone-${classId}`, zoneClick));
      map.on("click", "analysis-hotspot", hotspotClick);
      map.on("boxzoomend", () => {
        const bounds = map.getBounds();
        onDraftRef.current([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]);
      });
      setLoaded(true);
    });
    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      mapRef.current = null;
      map.remove();
    };
  }, [theme]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const zones = (result?.burn_zones ?? emptyCollection()) as GeoJSON.FeatureCollection;
    const hotspots = (result?.hotspots ?? emptyCollection()) as GeoJSON.FeatureCollection;
    const aoi: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: [
        ...(result ? [rectangle(result.request.bbox, "applied")] : []),
        ...(draftBBox && (!result || draftBBox.some((value, index) => value !== result.request.bbox[index]))
          ? [rectangle(draftBBox, "draft")]
          : []),
      ],
    };
    (map.getSource("analysis-zones") as GeoJSONSource).setData(zones);
    (map.getSource("analysis-hotspots") as GeoJSONSource).setData(hotspots);
    (map.getSource("analysis-aoi") as GeoJSONSource).setData(aoi);
  }, [draftBBox, loaded, result]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    ([1, 2, 3] as const).forEach((classId) => {
      map.setLayoutProperty(`analysis-zone-${classId}`, "visibility", zonesVisible ? "visible" : "none");
    });
    map.setLayoutProperty("analysis-hotspot", "visibility", hotspotsVisible ? "visible" : "none");
  }, [hotspotsVisible, loaded, zonesVisible]);

  const fit = useCallback(() => {
    const bbox = result?.request.bbox ?? draftBBox;
    if (!bbox) return;
    mapRef.current?.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 48, maxZoom: 12 });
  }, [draftBBox, result]);

  const visibleBounds = useCallback(() => {
    const bounds = mapRef.current?.getBounds();
    if (!bounds) return;
    onDraftBBox([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]);
  }, [onDraftBBox]);

  return (
    <section className={styles.mapCard} aria-label="Карта результата анализа">
      <div className={styles.mapHeader}>
        <div>
          <h2>Карта результата</h2>
          <p>
            {result
              ? `${result.request.from} — ${result.request.to} · ${result.result_id}`
              : "Область запроса, термоточки и зоны поражения"}
          </p>
        </div>
        <div className={styles.mapActions}>
          <button type="button" onClick={() => setHotspotsVisible((value) => !value)} aria-pressed={hotspotsVisible}>
            {hotspotsVisible ? <Eye size={14} /> : <EyeOff size={14} />} Термоточки
          </button>
          <button type="button" onClick={() => setZonesVisible((value) => !value)} aria-pressed={zonesVisible}>
            {zonesVisible ? <Eye size={14} /> : <EyeOff size={14} />} Гари
          </button>
          <button type="button" onClick={fit}><Focus size={14} /> Показать AOI</button>
        </div>
      </div>
      <div
        ref={containerRef}
        className={styles.mapCanvas}
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "Escape") popupRef.current?.remove();
        }}
      />
      <div className={styles.mapToolbar}>
        <button type="button" onClick={visibleBounds}><MousePointer2 size={14} /> Взять видимую область</button>
        <span>Shift + перетаскивание — выделить bbox</span>
      </div>
      <div className={styles.legend} aria-label="Легенда">
        <span><i data-class="hotspot" />Термоточка</span>
        <span><i data-class="low" />Слабая</span>
        <span><i data-class="moderate" />Средняя</span>
        <span><i data-class="high" />Сильная</span>
      </div>
      {basemapError && (
        <div className={styles.mapNotice} role="status">
          Внешняя подложка недоступна. Данные анализа, справка и экспорт продолжают работать.
        </div>
      )}
    </section>
  );
}
