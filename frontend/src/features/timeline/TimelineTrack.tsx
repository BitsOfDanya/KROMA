"use client";

import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { ObservationHistogram, SatellitePass, TimelineEvent } from "@/lib/api/types";
import { formatDate, formatDateTime, formatTime } from "@/lib/format";
import { ticksFor, WINDOW_MS, type TimeWindow, type WindowRange } from "@/lib/replay";
import { useWorkspace } from "@/state/workspace";

import styles from "./timeline.module.css";

const MARKED_KINDS = new Set(["detected", "confirmed", "priority_changed", "status_changed", "forecast_issued"]);

interface TimelineTrackProps {
  range: WindowRange;
  window: TimeWindow;
  histogram?: ObservationHistogram;
  events: TimelineEvent[];
  passes: SatellitePass[];
  selectedId: string | null;
  expanded: boolean;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

const Background = memo(function Background({
  range,
  window,
  histogram,
  events,
  passes,
  selectedId,
  expanded,
  width,
  height,
  onHover,
}: TimelineTrackProps & { width: number; height: number; onHover: (event: TimelineEvent | null, x: number) => void }) {
  const span = range.end - range.start;
  const x = (time: number) => ((time - range.start) / span) * width;
  const ticks = ticksFor(range, window);
  const histTop = expanded ? 26 : 20;
  const histHeight = expanded ? 34 : height - histTop - 12;
  const eventsY = expanded ? histTop + histHeight + 18 : histTop + histHeight + 2;
  const passesY = expanded ? eventsY + 24 : -100;
  const bins = histogram?.bins ?? [];
  const max = Math.max(1, ...bins.map((bin) => bin.total));
  const binWidth = histogram ? Math.max(1, (histogram.bin_minutes * 60_000 * width) / span - 1) : 0;
  const nowX = x(range.now);
  const multiDay = window === "3d" || window === "7d";

  const markers = events.filter((event) => MARKED_KINDS.has(event.kind));

  return (
    <svg aria-hidden="true">
      <rect x={nowX} y={0} width={Math.max(0, width - nowX)} height={height} fill="var(--surface-sunken)" opacity={0.6} />
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={x(tick)} x2={x(tick)} y1={14} y2={height} stroke="var(--border)" />
          <text className={styles.tickLabel} x={x(tick) + 4} y={11}>
            {multiDay && new Date(tick).getHours() === 0 ? formatDate(tick) : formatTime(tick)}
          </text>
        </g>
      ))}
      {bins.map((bin) => {
        const bx = x(new Date(bin.start).getTime());
        const total = (bin.total / max) * histHeight;
        const incident = (bin.incident / max) * histHeight;
        return (
          <g key={bin.start}>
            <rect x={bx} y={histTop + histHeight - total} width={binWidth} height={total} fill="var(--observation)" opacity={0.28} />
            <rect x={bx} y={histTop + histHeight - incident} width={binWidth} height={incident} fill="var(--observation)" opacity={0.75} />
          </g>
        );
      })}
      {expanded && (
        <>
          <text className={styles.laneLabel} x={6} y={histTop + 8}>Наблюдения</text>
          <text className={styles.laneLabel} x={6} y={eventsY - 8}>События</text>
          <text className={styles.laneLabel} x={6} y={passesY - 8}>Пролёты{selectedId ? ` · ${selectedId}` : ""}</text>
          <line x1={0} x2={width} y1={eventsY} y2={eventsY} stroke="var(--border)" />
          <line x1={0} x2={width} y1={passesY} y2={passesY} stroke="var(--border)" />
        </>
      )}
      {markers.map((event) => {
        const mx = x(new Date(event.occurred_at).getTime());
        const mine = selectedId !== null && event.incident_id === selectedId;
        const color =
          event.kind === "confirmed"
            ? "var(--confirmed)"
            : event.kind === "priority_changed"
              ? "var(--incident-high)"
              : event.kind === "forecast_issued"
                ? "var(--forecast-80)"
                : "var(--text-secondary)";
        const size = mine ? 4 : 3;
        return (
          <path
            key={event.id}
            d={`M${mx} ${eventsY - size} L${mx + size} ${eventsY} L${mx} ${eventsY + size} L${mx - size} ${eventsY} Z`}
            fill={color}
            opacity={selectedId && !mine ? 0.3 : 0.95}
            style={{ pointerEvents: "all", cursor: "pointer" }}
            onPointerEnter={() => onHover(event, mx)}
            onPointerLeave={() => onHover(null, 0)}
          />
        );
      })}
      {expanded &&
        passes.map((item) => {
          const px = x(new Date(item.overpass_at).getTime());
          if (px < 0 || px > width) return null;
          const future = new Date(item.overpass_at).getTime() > range.now;
          return (
            <g key={item.id}>
              <path
                d={`M${px} ${passesY - 5} L${px + 4} ${passesY + 3} L${px - 4} ${passesY + 3} Z`}
                fill={future ? "none" : item.kind === "optical" ? "var(--confirmed)" : "var(--observation)"}
                stroke={item.kind === "optical" ? "var(--confirmed)" : "var(--observation)"}
                strokeWidth={1.2}
              />
              {future && (
                <text className={styles.tickLabel} x={px + 6} y={passesY + 4}>
                  {item.satellite}
                </text>
              )}
            </g>
          );
        })}
      <line x1={nowX} x2={nowX} y1={14} y2={height} stroke="var(--confirmed)" strokeWidth={1} />
    </svg>
  );
});

export function TimelineTrack(props: TimelineTrackProps) {
  const { range, window, expanded } = props;
  const [ref, width] = useWidth<HTMLDivElement>();
  const cursor = useWorkspace((state) => state.cursor);
  const setCursor = useWorkspace((state) => state.setCursor);
  const setPlaying = useWorkspace((state) => state.setPlaying);
  const [hovered, setHovered] = useState<{ event: TimelineEvent; x: number } | null>(null);
  const [height, setHeight] = useState(0);
  const dragging = useRef(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setHeight(entry.contentRect.height));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);

  const timeAt = useCallback(
    (clientX: number) => {
      const rect = ref.current?.getBoundingClientRect();
      if (!rect) return null;
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      const time = range.start + ratio * (range.end - range.start);
      return time >= range.now ? null : time;
    },
    [ref, range],
  );

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    setPlaying(false);
    setCursor(timeAt(event.clientX));
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (dragging.current) setCursor(timeAt(event.clientX));
  };
  const onPointerUp = () => {
    dragging.current = false;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = WINDOW_MS[window] / 48;
    const current = cursor ?? range.now;
    let next: number | null | undefined;
    if (event.key === "ArrowLeft") next = Math.max(range.start, current - step);
    if (event.key === "ArrowRight") next = current + step >= range.now ? null : current + step;
    if (event.key === "Home") next = range.start;
    if (event.key === "End") next = null;
    if (next === undefined) return;
    event.preventDefault();
    setPlaying(false);
    setCursor(next);
  };

  const onHover = useCallback((event: TimelineEvent | null, x: number) => setHovered(event ? { event, x } : null), []);

  const cursorX = cursor !== null && width ? ((cursor - range.start) / (range.end - range.start)) * width : null;
  const valueText = cursor === null ? "Сейчас" : formatDateTime(cursor);

  const background = useMemo(
    () => (width > 0 && height > 0 ? <Background {...props} width={width} height={height} onHover={onHover} /> : null),
    [props, width, height, onHover],
  );

  return (
    <div
      ref={ref}
      className={styles.track}
      role="slider"
      tabIndex={0}
      aria-label="Время на хронологии"
      aria-valuemin={range.start}
      aria-valuemax={range.now}
      aria-valuenow={cursor ?? range.now}
      aria-valuetext={valueText}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onKeyDown}
    >
      {background}
      {cursorX !== null && (
        <svg aria-hidden="true" style={{ pointerEvents: "none" }}>
          <line x1={cursorX} x2={cursorX} y1={0} y2="100%" stroke="var(--text)" strokeWidth={1.5} />
          <circle cx={cursorX} cy={expanded ? 16 : 14} r={4} fill="var(--text)" />
        </svg>
      )}
      {hovered && (
        <div className={styles.eventTooltip} style={{ left: hovered.x }}>
          {hovered.event.incident_id && <span className="mono">{hovered.event.incident_id} · </span>}
          {hovered.event.title} · {formatTime(hovered.event.occurred_at)}
        </div>
      )}
    </div>
  );
}
