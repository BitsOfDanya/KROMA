"use client";

import type { GeoJSONSource, MapGeoJSONFeature, MapMouseEvent } from "maplibre-gl";
import Link from "next/link";
import { ArrowUpRight, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { formatArea, formatDistance, formatExact, formatInteger, formatRelative, pluralize } from "@/lib/format";
import { pathLengthKm } from "@/lib/geo";
import { SEVERITY_LABEL, STATUS_LABEL, RISK_KIND_LABEL } from "@/lib/labels";
import type { IncidentStatus, Position, RiskObjectKind, Severity } from "@/lib/api/types";
import { useWorkspace } from "@/state/workspace";

import { BURN_SCAR_FILL_LAYER } from "./layers/burnScars";
import { HOTSPOT_CLUSTER_LAYER, HOTSPOT_POINT_LAYER, HOTSPOTS_SOURCE, INCIDENT_OBSERVATION_LAYER } from "./layers/hotspots";
import { INCIDENT_CLUSTER_LAYER, INCIDENT_INTERACTIVE_LAYERS, INCIDENTS_SOURCE } from "./layers/incidents";
import { MEASURE_SOURCE } from "./layers/measure";
import { RISK_INTERACTIVE_LAYERS } from "./layers/riskObjects";
import { THERMAL_LAYER } from "./layers/thermal";
import { useMapContext } from "./MapContext";
import styles from "./map.module.css";

const INTERACTIVE = [
  ...INCIDENT_INTERACTIVE_LAYERS,
  INCIDENT_CLUSTER_LAYER,
  HOTSPOT_CLUSTER_LAYER,
  HOTSPOT_POINT_LAYER,
  INCIDENT_OBSERVATION_LAYER,
  THERMAL_LAYER,
  ...RISK_INTERACTIVE_LAYERS,
  BURN_SCAR_FILL_LAYER,
];

interface HoverState {
  x: number;
  y: number;
  layer: string;
  properties: Record<string, unknown>;
  source: string;
  pinned: boolean;
}

function HoverContent({ state }: { state: HoverState }) {
  const p = state.properties;
  const layer = state.layer;
  if (INCIDENT_INTERACTIVE_LAYERS.includes(layer)) {
    const isLive = p.detection_count !== undefined;
    return (
      <>
        <div className={styles.hoverTitle}>
          <span className="mono">{String(p.id)}</span>
          {!isLive && <span>{String(p.district)}</span>}
        </div>
        <dl className={styles.hoverRows}>
          <dt>Статус</dt>
          <dd>{STATUS_LABEL[p.status as IncidentStatus]}</dd>
          <dt>Уровень</dt>
          <dd>{SEVERITY_LABEL[p.severity as Severity]}</dd>
          <dt>Priority</dt>
          <dd>{String(p.priority)}</dd>
          {isLive ? (
            <>
              <dt>Детекций</dt>
              <dd>{String(p.detection_count)}</dd>
              <dt>FRP</dt>
              <dd>{Number(p.frp_mw).toFixed(0)} МВт</dd>
              <dt>Обновлён</dt>
              <dd>{formatRelative(Number(p.updated) * 1000)}</dd>
            </>
          ) : (
            <>
              <dt>Площадь</dt>
              <dd>{formatArea(Number(p.area_ha))}</dd>
            </>
          )}
        </dl>
      </>
    );
  }
  if (layer === HOTSPOT_POINT_LAYER || layer === INCIDENT_OBSERVATION_LAYER) {
    const time = Number(p.t) * 1000;
    return (
      <>
        <div className={styles.hoverTitle}>
          {String(p.satellite)} · {String(p.instrument)}
        </div>
        <dl className={styles.hoverRows}>
          <dt>Время</dt>
          <dd title={formatExact(time)}>{formatRelative(time)}</dd>
          <dt>FRP</dt>
          <dd>{Number(p.frp_mw).toFixed(1)} МВт</dd>
          <dt>Пиксель</dt>
          <dd>{String(p.pixel_size_m)} м</dd>
          <dt>Достоверность</dt>
          <dd>{p.confidence === "h" ? "высокая" : p.confidence === "n" ? "номинальная" : "низкая"}</dd>
          <dt>Связь</dt>
          <dd>
            {p.classification === "incident"
              ? String(p.incident_id)
              : p.classification === "persistent_source"
                ? "постоянный источник"
                : "не в событии"}
          </dd>
        </dl>
      </>
    );
  }
  if (layer === THERMAL_LAYER) {
    return (
      <>
        <div className={styles.hoverTitle}>Постоянный тепловой источник</div>
        <div style={{ marginBottom: 6 }}>{String(p.name)}</div>
        <dl className={styles.hoverRows}>
          <dt>Наблюдений</dt>
          <dd>{formatInteger(Number(p.observation_count))}</dd>
          <dt>История</dt>
          <dd>{Number(p.history_years).toLocaleString("ru-RU")} года</dd>
          <dt>Средний FRP</dt>
          <dd>{Number(p.mean_frp_mw).toFixed(0)} МВт</dd>
        </dl>
      </>
    );
  }
  if (layer === BURN_SCAR_FILL_LAYER) {
    return (
      <>
        <div className={styles.hoverTitle}>{String(p.name)}</div>
        <dl className={styles.hoverRows}>
          <dt>Площадь</dt>
          <dd>{formatArea(Number(p.area_ha))}</dd>
          <dt>Оценка</dt>
          <dd>{p.assessment === "final" ? "итоговая" : "предварительная"}</dd>
        </dl>
        {state.pinned && (
          <Link className={styles.hoverAction} href={`/analytics?scar=${encodeURIComponent(String(p.id))}`}>
            Сравнение до / после <ArrowUpRight size={13} />
          </Link>
        )}
        {!state.pinned && <div style={{ marginTop: 6, color: "var(--text-tertiary)" }}>Нажмите, чтобы открыть</div>}
      </>
    );
  }
  if (RISK_INTERACTIVE_LAYERS.includes(layer)) {
    return (
      <>
        <div className={styles.hoverTitle}>{String(p.name)}</div>
        <div>
          {RISK_KIND_LABEL[p.kind as RiskObjectKind]} · {String(p.subtitle)}
        </div>
        {p.population ? <div style={{ marginTop: 4 }}>{pluralize(Number(p.population), ["житель", "жителя", "жителей"])}</div> : null}
      </>
    );
  }
  return null;
}

export function MapInteractions() {
  const { map, layers } = useMapContext();
  const [hover, setHover] = useState<HoverState | null>(null);
  const hoveredIncident = useRef<{ source: string; id: string } | null>(null);
  const measuring = useWorkspace((state) => state.measuring);
  const setMeasuring = useWorkspace((state) => state.setMeasuring);
  const [points, setPoints] = useState<Position[]>([]);
  const measuringRef = useRef(measuring);

  useEffect(() => {
    measuringRef.current = measuring;
  }, [measuring]);

  const setMeasuringAndClear = (value: boolean) => {
    if (!value) setPoints([]);
    setMeasuring(value);
  };

  useEffect(() => {
    const features: GeoJSON.Feature[] = points.map((point, index) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: point },
      properties: index === points.length - 1 && index > 0 ? { label: formatDistance(pathLengthKm(points)) } : {},
    }));
    if (points.length > 1) features.push({ type: "Feature", geometry: { type: "LineString", coordinates: points }, properties: {} });
    layers.setData(map, MEASURE_SOURCE, { type: "FeatureCollection", features });
  }, [map, layers, points]);

  useEffect(() => {
    if (!map) return;
    const canvas = map.getCanvasContainer();
    let frame = 0;

    const setIncidentHover = (next: { source: string; id: string } | null) => {
      const previous = hoveredIncident.current;
      if (previous && (!next || previous.id !== next.id || previous.source !== next.source)) {
        if (map.getSource(previous.source)) map.setFeatureState({ source: previous.source, id: previous.id }, { hover: false });
      }
      if (next && map.getSource(next.source)) map.setFeatureState({ source: next.source, id: next.id }, { hover: true });
      hoveredIncident.current = next;
    };

    const topFeature = (point: MapMouseEvent["point"]): MapGeoJSONFeature | undefined => {
      const available = INTERACTIVE.filter((id) => map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== "none");
      if (available.length === 0) return undefined;
      return map.queryRenderedFeatures(point, { layers: available })[0];
    };

    const onMove = (event: MapMouseEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (measuringRef.current) return;
        const feature = topFeature(event.point);
        canvas.style.cursor = feature ? "pointer" : "";
        const isIncident = feature && INCIDENT_INTERACTIVE_LAYERS.includes(feature.layer.id);
        setIncidentHover(isIncident ? { source: feature.source, id: String(feature.properties.id) } : null);
        setHover((current) => {
          if (current?.pinned) return current;
          if (!feature || feature.layer.id === INCIDENT_CLUSTER_LAYER || feature.layer.id === HOTSPOT_CLUSTER_LAYER) return null;
          return {
            x: event.point.x,
            y: event.point.y,
            layer: feature.layer.id,
            source: feature.source,
            properties: feature.properties,
            pinned: false,
          };
        });
      });
    };

    const onLeave = () => {
      canvas.style.cursor = "";
      setIncidentHover(null);
      setHover((current) => (current?.pinned ? current : null));
    };

    const onClick = async (event: MapMouseEvent) => {
      if (measuringRef.current) {
        setPoints((current) => [...current, [event.lngLat.lng, event.lngLat.lat]]);
        return;
      }
      const feature = topFeature(event.point);
      if (!feature) {
        setHover(null);
        return;
      }
      const layerId = feature.layer.id;
      if (layerId === INCIDENT_CLUSTER_LAYER || layerId === HOTSPOT_CLUSTER_LAYER) {
        const sourceId = layerId === INCIDENT_CLUSTER_LAYER ? INCIDENTS_SOURCE : HOTSPOTS_SOURCE;
        const clusterId = feature.properties.cluster_id;
        const geometry = feature.geometry as GeoJSON.Point;
        if (typeof clusterId === "number") {
          const zoom = await (map.getSource(sourceId) as GeoJSONSource).getClusterExpansionZoom(clusterId);
          map.easeTo({ center: geometry.coordinates as [number, number], zoom: Math.min(zoom + 0.3, 12), duration: 700 });
        } else {
          map.easeTo({ center: geometry.coordinates as [number, number], zoom: map.getZoom() + 2, duration: 700 });
        }
        return;
      }
      if (INCIDENT_INTERACTIVE_LAYERS.includes(layerId)) {
        if (useWorkspace.getState().appMode === "live") {
          setHover({
            x: event.point.x,
            y: event.point.y,
            layer: layerId,
            source: feature.source,
            properties: feature.properties,
            pinned: true,
          });
          return;
        }
        const id = String(feature.properties.id);
        useWorkspace.getState().selectIncident(id);
        setHover(null);
        return;
      }
      if (layerId === BURN_SCAR_FILL_LAYER || layerId === THERMAL_LAYER || RISK_INTERACTIVE_LAYERS.includes(layerId)) {
        setHover({
          x: event.point.x,
          y: event.point.y,
          layer: layerId,
          source: feature.source,
          properties: feature.properties,
          pinned: true,
        });
      }
    };

    map.on("mousemove", onMove);
    map.on("mouseout", onLeave);
    map.on("click", onClick);
    return () => {
      cancelAnimationFrame(frame);
      map.off("mousemove", onMove);
      map.off("mouseout", onLeave);
      map.off("click", onClick);
    };
  }, [map]);

  useEffect(() => {
    if (!map) return;
    const container = map.getContainer();
    container.classList.toggle(styles.measuring, measuring);
    if (measuring) map.doubleClickZoom.disable();
    else map.doubleClickZoom.enable();
  }, [map, measuring]);

  return (
    <>
      {hover && (
        <div className={styles.hoverCard} style={{ left: hover.x, top: hover.y }} data-pinned={hover.pinned} role="tooltip">
          {hover.pinned && (
            <IconButton
              label="Закрыть"
              size="sm"
              showTooltip={false}
              icon={<X size={13} />}
              style={{ position: "absolute", right: 4, top: 4 }}
              onClick={() => setHover(null)}
            />
          )}
          <HoverContent state={hover} />
        </div>
      )}
      {measuring && (
        <div className={styles.measureReadout} role="status">
          {points.length < 2 ? (
            <span>Кликните по карте, чтобы добавить точки</span>
          ) : (
            <span>
              Расстояние <strong>{formatDistance(pathLengthKm(points))}</strong>
            </span>
          )}
          {points.length > 0 && (
            <button type="button" className="mono" style={{ color: "var(--text-secondary)" }} onClick={() => setPoints([])}>
              Сброс
            </button>
          )}
          <IconButton label="Завершить измерение" size="sm" showTooltip={false} icon={<X size={14} />} onClick={() => setMeasuringAndClear(false)} />
        </div>
      )}
    </>
  );
}
