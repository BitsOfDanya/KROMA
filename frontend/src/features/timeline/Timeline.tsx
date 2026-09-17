"use client";

import { ChevronDown, ChevronUp, Pause, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useIncidentTimeline, useObservationHistogram, useTimelineEvents } from "@/lib/api/queries";
import { formatDateLong, formatTime } from "@/lib/format";
import { windowRange, type ReplaySpeed, type TimeWindow } from "@/lib/replay";
import { useWorkspace } from "@/state/workspace";

import styles from "./timeline.module.css";
import { TimelineTrack } from "./TimelineTrack";
import { useReplayClock } from "./useReplayClock";

const HOUR = 3_600_000;

function useNow(interval = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  const playing = useWorkspace((state) => state.playing);
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!useWorkspace.getState().playing) setNow(Date.now());
    }, interval);
    return () => window.clearInterval(timer);
  }, [interval, playing]);
  return now;
}

export function Timeline() {
  useReplayClock();
  const now = useNow();
  const timeWindow = useWorkspace((state) => state.timeWindow);
  const setTimeWindow = useWorkspace((state) => state.setTimeWindow);
  const cursor = useWorkspace((state) => state.cursor);
  const setCursor = useWorkspace((state) => state.setCursor);
  const playing = useWorkspace((state) => state.playing);
  const setPlaying = useWorkspace((state) => state.setPlaying);
  const speed = useWorkspace((state) => state.speed);
  const setSpeed = useWorkspace((state) => state.setSpeed);
  const expanded = useWorkspace((state) => state.timelineExpanded);
  const toggleExpanded = useWorkspace((state) => state.toggleTimelineExpanded);
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const appMode = useWorkspace((state) => state.appMode);
  const isReplay = appMode === "replay";

  const hourNow = Math.ceil(now / HOUR) * HOUR;
  const range = useMemo(() => windowRange(timeWindow, now), [timeWindow, now]);
  const fromIso = new Date(hourNow - (range.now - range.start) - HOUR).toISOString();
  const toIso = new Date(hourNow).toISOString();
  const histogramFrom = new Date(range.start - (range.start % (5 * 60_000))).toISOString();
  const histogramTo = new Date(range.now - (range.now % (5 * 60_000))).toISOString();

  const events = useTimelineEvents(fromIso, toIso, isReplay);
  const histogram = useObservationHistogram(histogramFrom, histogramTo, 96, isReplay);
  const incidentTimeline = useIncidentTimeline(isReplay ? selectedId : null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.code !== "Space" || ["INPUT", "TEXTAREA", "BUTTON", "SELECT"].includes(target.tagName) || target.getAttribute("role") === "radio") return;
      event.preventDefault();
      const state = useWorkspace.getState();
      state.setPlaying(!state.playing);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const shown = cursor ?? now;
  const live = cursor === null;

  return (
    <section
      className={styles.dock}
      aria-label="Хронология и ретроспектива"
      style={{ ["--timeline-current" as string]: expanded ? "150px" : "68px" }}
    >
      <div className={styles.clock}>
        <span className={styles.clockDate}>{formatDateLong(shown)}</span>
        <span className={styles.clockTime}>{formatTime(shown)}</span>
        <span className={styles.clockState} data-live={live}>
          {live && <span className={styles.liveDot} />}
          {live ? "Оперативно" : playing ? "Воспроизведение" : isReplay ? "Ретроспектива" : "История"}
        </span>
      </div>
      <TimelineTrack
        range={range}
        window={timeWindow}
        histogram={histogram.data}
        events={events.data?.events ?? []}
        passes={incidentTimeline.data?.passes ?? []}
        selectedId={selectedId}
        expanded={expanded}
      />
      <div className={styles.controls}>
        {isReplay && (
          <div className={styles.controlCluster}>
            <button
              type="button"
              className={styles.play}
              aria-label={playing ? "Пауза" : "Воспроизвести развитие"}
              onClick={() => setPlaying(!playing)}
            >
              {playing ? <Pause size={15} fill="currentColor" /> : <Play size={15} fill="currentColor" style={{ marginLeft: 2 }} />}
            </button>
            <SegmentedControl<ReplaySpeed>
              className={styles.speedControl}
              label="Скорость воспроизведения"
              size="sm"
              value={speed}
              onChange={setSpeed}
              options={[
                { value: 1, label: "1×" },
                { value: 4, label: "4×" },
                { value: 12, label: "12×" },
              ]}
            />
          </div>
        )}
        <div className={styles.controlCluster}>
          <button
            type="button"
            className={styles.liveButton}
            disabled={live}
            onClick={() => {
              setPlaying(false);
              setCursor(null);
            }}
          >
            Сейчас
          </button>
          <SegmentedControl<TimeWindow>
            className={styles.windowControl}
            label="Окно времени"
            size="sm"
            value={timeWindow}
            onChange={setTimeWindow}
            options={[
              { value: "6h", label: "6 ч" },
              { value: "24h", label: "24 ч" },
              { value: "3d", label: "3 д" },
              { value: "7d", label: "7 д" },
            ]}
          />
        </div>
        <IconButton
          label={expanded ? "Свернуть хронологию" : "Развернуть хронологию"}
          tooltipSide="top"
          icon={expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
          onClick={toggleExpanded}
        />
      </div>
    </section>
  );
}
