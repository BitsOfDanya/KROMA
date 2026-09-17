import type { IncidentSnapshot, IncidentStatus, IncidentSummary, Severity } from "./api/types";
import { severityForPriority } from "./labels";

export type TimeWindow = "6h" | "24h" | "3d" | "7d";
export type ReplaySpeed = 1 | 4 | 12;

export const WINDOW_MS: Record<TimeWindow, number> = {
  "6h": 6 * 3_600_000,
  "24h": 24 * 3_600_000,
  "3d": 3 * 24 * 3_600_000,
  "7d": 7 * 24 * 3_600_000,
};

export const REPLAY_BASE_DURATION_MS = 60_000;
export const FUTURE_SHARE = 0.08;

export interface IncidentState {
  visible: boolean;
  status: IncidentStatus;
  severity: Severity;
  confidence: number;
  threat: number;
  priority: number;
  area_ha: number;
  frp_mw: number;
  observation_count: number;
  observed_at: string | null;
}

export function snapshotIndexAt(snapshots: IncidentSnapshot[], time: number): number {
  let low = 0;
  let high = snapshots.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (new Date(snapshots[middle].observed_at).getTime() <= time) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

export function incidentStateAtIndex(incident: IncidentSummary, index: number | null): IncidentState {
  if (index === null) {
    return {
      visible: true,
      status: incident.status,
      severity: incident.severity,
      confidence: incident.confidence,
      threat: incident.threat,
      priority: incident.priority,
      area_ha: incident.area_ha,
      frp_mw: incident.frp_mw,
      observation_count: incident.observation_count,
      observed_at: incident.snapshots.at(-1)?.observed_at ?? null,
    };
  }
  if (index < 0) {
    return {
      visible: false,
      status: incident.snapshots[0]?.status ?? incident.status,
      severity: "low",
      confidence: 0,
      threat: 0,
      priority: 0,
      area_ha: 0,
      frp_mw: 0,
      observation_count: 0,
      observed_at: null,
    };
  }
  const snapshot = incident.snapshots[index];
  return {
    visible: true,
    status: snapshot.status,
    severity: severityForPriority(snapshot.priority),
    confidence: snapshot.confidence,
    threat: snapshot.threat,
    priority: snapshot.priority,
    area_ha: snapshot.area_ha,
    frp_mw: snapshot.frp_mw,
    observation_count: snapshot.observation_count,
    observed_at: snapshot.observed_at,
  };
}

export function incidentStateAt(incident: IncidentSummary, time: number | null): IncidentState {
  return incidentStateAtIndex(incident, time === null ? null : snapshotIndexAt(incident.snapshots, time));
}

export function parseStateKey(key: string): (number | null)[] | null {
  if (key === "live") return null;
  return key.split(",").map(Number);
}

export function stateKey(incidents: IncidentSummary[], time: number | null): string {
  if (time === null) return "live";
  return incidents.map((incident) => snapshotIndexAt(incident.snapshots, time)).join(",");
}

export interface WindowRange {
  start: number;
  end: number;
  now: number;
}

export function windowRange(window: TimeWindow, now: number): WindowRange {
  const span = WINDOW_MS[window];
  return { start: now - span, end: now + span * FUTURE_SHARE, now };
}

export function replayStep(window: TimeWindow, speed: ReplaySpeed, elapsedMs: number): number {
  return (WINDOW_MS[window] / REPLAY_BASE_DURATION_MS) * speed * elapsedMs;
}

export function advanceCursor(
  cursor: number | null,
  window: TimeWindow,
  speed: ReplaySpeed,
  elapsedMs: number,
  now: number,
): { cursor: number | null; finished: boolean } {
  const start = now - WINDOW_MS[window];
  const current = cursor === null || cursor >= now ? start : Math.max(cursor, start);
  const next = current + replayStep(window, speed, elapsedMs);
  if (next >= now) return { cursor: null, finished: true };
  return { cursor: next, finished: false };
}

export function ticksFor(range: WindowRange, window: TimeWindow): number[] {
  const hour = 3_600_000;
  const step = window === "6h" ? hour : window === "24h" ? 3 * hour : window === "3d" ? 12 * hour : 24 * hour;
  const offset = new Date(range.start).getTimezoneOffset() * 60_000;
  const first = Math.ceil((range.start - offset) / step) * step + offset;
  const ticks: number[] = [];
  for (let tick = first; tick <= range.end; tick += step) ticks.push(tick);
  return ticks;
}

export function histogram(times: Float64Array | number[], range: WindowRange, bins: number): number[] {
  const counts = new Array<number>(bins).fill(0);
  const span = range.end - range.start;
  for (const time of times) {
    if (time < range.start || time > range.end) continue;
    const index = Math.min(bins - 1, Math.floor(((time - range.start) / span) * bins));
    counts[index] += 1;
  }
  return counts;
}
