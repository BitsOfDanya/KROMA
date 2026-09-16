import { describe, expect, it } from "vitest";

import type { IncidentSummary } from "./api/types";
import { advanceCursor, histogram, incidentStateAt, snapshotIndexAt, WINDOW_MS, windowRange } from "./replay";

const snapshots = [
  { observed_at: "2026-09-16T00:00:00Z", status: "suspected", confidence: 41, threat: 34, priority: 38, area_ha: 35, frp_mw: 18, observation_count: 2 },
  { observed_at: "2026-09-16T06:00:00Z", status: "confirmed", confidence: 88, threat: 61, priority: 66, area_ha: 420, frp_mw: 132, observation_count: 19 },
  { observed_at: "2026-09-16T11:00:00Z", status: "confirmed", confidence: 96, threat: 88, priority: 91, area_ha: 1860, frp_mw: 356, observation_count: 120 },
] as IncidentSummary["snapshots"];

const incident = {
  id: "KR-042",
  status: "confirmed",
  severity: "critical",
  confidence: 96,
  threat: 88,
  priority: 91,
  area_ha: 1860,
  frp_mw: 356,
  observation_count: 120,
  snapshots,
} as IncidentSummary;

describe("incident replay state", () => {
  it("finds the latest snapshot not after the cursor", () => {
    expect(snapshotIndexAt(snapshots, Date.parse("2026-09-15T23:00:00Z"))).toBe(-1);
    expect(snapshotIndexAt(snapshots, Date.parse("2026-09-16T06:00:00Z"))).toBe(1);
    expect(snapshotIndexAt(snapshots, Date.parse("2026-09-16T10:59:00Z"))).toBe(1);
  });

  it("hides incidents before first detection and derives severity from priority", () => {
    expect(incidentStateAt(incident, Date.parse("2026-09-15T12:00:00Z")).visible).toBe(false);
    const state = incidentStateAt(incident, Date.parse("2026-09-16T07:00:00Z"));
    expect(state).toMatchObject({ visible: true, priority: 66, severity: "high", status: "confirmed" });
  });

  it("returns live values when no cursor is set", () => {
    expect(incidentStateAt(incident, null).priority).toBe(91);
  });
});

describe("replay clock", () => {
  const now = Date.parse("2026-09-16T12:00:00Z");

  it("starts from the window start when live", () => {
    const { cursor } = advanceCursor(null, "24h", 1, 1000, now);
    expect(cursor).toBe(now - WINDOW_MS["24h"] + WINDOW_MS["24h"] / 60);
  });

  it("finishes at now", () => {
    expect(advanceCursor(now - 1000, "6h", 12, 1000, now)).toEqual({ cursor: null, finished: true });
  });

  it("bins observations into a histogram", () => {
    const range = windowRange("6h", now);
    const counts = histogram([now - 1000, now - 1000, range.start + 1, now - WINDOW_MS["24h"]], range, 10);
    expect(counts.reduce((a, b) => a + b, 0)).toBe(3);
    expect(counts[0]).toBe(1);
  });
});
