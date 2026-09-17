"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import { AttributionControl, Map as MapLibreMap, ScaleControl } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { INITIAL_VIEW } from "@/config/map";
import { useTheme } from "@/state/theme";
import { useWorkspace } from "@/state/workspace";

import { buildBasemapStyle } from "./basemap";
import "./mapWorker";
import { cameraPadding } from "./camera";
import { registerMapImages } from "./images";
import { OperationalLayers } from "./layers";
import { INCIDENT_PULSE_LAYER } from "./layers/incidents";
import { MapContext } from "./MapContext";
import styles from "./map.module.css";
import { readPalette } from "./palette";


export interface MapView {
  center: [number, number];
  zoom: number;
}

interface KromaMapProps {
  initialView?: MapView | null;
  onViewChange?: (view: MapView) => void;
  children?: ReactNode;
  interactive?: boolean;
}

function webglAvailable() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function KromaMap({ initialView, onViewChange, children }: KromaMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<MapLibreMap | null>(null);
  const [styleVersion, setStyleVersion] = useState(0);
  const [failure, setFailure] = useState<string | null>(null);
  const layers = useMemo(() => new OperationalLayers(), []);
  const { theme } = useTheme();
  const basemap = useWorkspace((state) => state.basemap);
  const viewCallback = useRef(onViewChange);
  const initialViewRef = useRef(initialView);

  useEffect(() => {
    viewCallback.current = onViewChange;
  }, [onViewChange]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!webglAvailable()) {
      queueMicrotask(() => setFailure("Браузер не поддерживает WebGL — карта недоступна."));
      return;
    }
    const start = initialViewRef.current ?? INITIAL_VIEW;
    const state = useWorkspace.getState();
    const instance = new MapLibreMap({
      container,
      style: buildBasemapStyle(state.basemap, document.documentElement.dataset.theme === "light" ? "light" : "dark", readPalette()),
      center: start.center,
      zoom: start.zoom,
      minZoom: 1.4,
      maxZoom: 15,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      fadeDuration: 180,
      renderWorldCopies: true,
    });
    instance.touchZoomRotate.disableRotation();
    instance.keyboard.disableRotation();
    instance.addControl(new AttributionControl({ compact: true }), "bottom-right");
    instance.addControl(new ScaleControl({ maxWidth: 96, unit: "metric" }), "bottom-right");

    let tileErrors = 0;
    instance.on("error", (event) => {
      const message = String(event.error?.message ?? "");
      if (/tile|Failed to fetch|NetworkError|AJAXError/i.test(message)) {
        tileErrors += 1;
        if (tileErrors === 25 && !instance.loaded()) setFailure("Картографические тайлы недоступны. Проверьте сеть или провайдера в конфигурации.");
      }
    });

    const onStyleLoad = () => {
      const current = useWorkspace.getState();
      registerMapImages(instance);
      layers.install(instance, readPalette(), { layers: current.layers, evidenceMode: current.evidenceMode });
      setStyleVersion((version) => version + 1);
    };
    instance.on("style.load", onStyleLoad);
    instance.on("styleimagemissing", () => registerMapImages(instance));

    instance.on("moveend", () => {
      const center = instance.getCenter();
      viewCallback.current?.({ center: [center.lng, center.lat], zoom: instance.getZoom() });
    });

    let frame = 0;
    let last = 0;
    const pulse = (time: number) => {
      frame = requestAnimationFrame(pulse);
      if (time - last < 40 || document.hidden) return;
      last = time;
      if (!instance.getLayer(INCIDENT_PULSE_LAYER)) return;
      const phase = (time % 2600) / 2600;
      const eased = 1 - (1 - phase) ** 2;
      instance.setPaintProperty(INCIDENT_PULSE_LAYER, "circle-radius", 11 + eased * 16);
      instance.setPaintProperty(INCIDENT_PULSE_LAYER, "circle-stroke-opacity", 0.55 * (1 - phase));
    };
    frame = requestAnimationFrame(pulse);

    queueMicrotask(() => setMap(instance));
    return () => {
      cancelAnimationFrame(frame);
      instance.remove();
      setMap(null);
    };
  }, [layers]);

  const styleKey = `${basemap}:${theme}`;
  const appliedStyle = useRef(styleKey);
  useEffect(() => {
    if (!map || appliedStyle.current === styleKey) return;
    appliedStyle.current = styleKey;
    map.setStyle(buildBasemapStyle(basemap, theme, readPalette()), { diff: false });
  }, [map, styleKey, basemap, theme]);

  useEffect(() => {
    if (!map) return;
    return useWorkspace.subscribe((state, previous) => {
      if (state.layers !== previous.layers || state.evidenceMode !== previous.evidenceMode) {
        layers.applyVisibility(map, { layers: state.layers, evidenceMode: state.evidenceMode });
      }
      if (state.camera && state.camera !== previous.camera) {
        const request = state.camera;
        const padding = cameraPadding(map.getContainer());
        if (request.kind === "bounds") {
          map.fitBounds(
            [
              [request.bbox[0], request.bbox[1]],
              [request.bbox[2], request.bbox[3]],
            ],
            { padding, maxZoom: request.maxZoom ?? 11, duration: 1600, essential: true },
          );
        } else {
          map.flyTo({ center: request.center, zoom: request.zoom, padding, duration: 1500, essential: true });
        }
      }
    });
  }, [map, layers]);

  const contextValue = useMemo(() => ({ map, styleVersion, layers }), [map, styleVersion, layers]);

  return (
    <MapContext.Provider value={contextValue}>
      <div className={styles.mapRoot}>
        <div ref={containerRef} className={styles.canvas} role="region" aria-label="Оперативная карта" />
        {failure && (
          <div className={styles.mapFailure} role="alert">
            <strong>Карта недоступна</strong>
            <span>{failure}</span>
          </div>
        )}
        {map && children}
      </div>
    </MapContext.Provider>
  );
}
