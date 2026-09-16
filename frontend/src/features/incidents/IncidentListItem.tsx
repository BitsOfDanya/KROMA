"use client";

import { memo } from "react";

import { SeverityMark, StatusGlyph } from "@/components/ui/StatusPill";
import type { IncidentSummary } from "@/lib/api/types";
import { formatDistance, formatExact, formatRelative } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/labels";
import type { IncidentState } from "@/lib/replay";

import styles from "./incidents.module.css";

interface IncidentListItemProps {
  incident: IncidentSummary;
  state: IncidentState;
  selected: boolean;
  now: number;
  onSelect: (id: string) => void;
}

export const IncidentListItem = memo(function IncidentListItem({ incident, state, selected, now, onSelect }: IncidentListItemProps) {
  return (
    <li>
      <button
        type="button"
        className={styles.item}
        aria-current={selected}
        data-hidden={!state.visible}
        onClick={() => onSelect(incident.id)}
      >
        <span className={styles.priority} title={`Priority ${state.priority}`}>
          <span className={styles.priorityValue}>{state.visible ? state.priority : "—"}</span>
          <SeverityMark severity={state.severity} />
        </span>
        <span className={styles.itemTitle}>
          <span className="mono">{incident.id}</span>
          <span className={styles.itemDistrict}>{incident.district}</span>
        </span>
        <span className={styles.itemSide}>
          {incident.is_new ? <span className={styles.newTag}>NEW</span> : <span />}
          <span title={formatExact(incident.updated_at)}>{formatRelative(incident.updated_at, now)}</span>
        </span>
        <span className={styles.itemMeta}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <StatusGlyph status={state.status} />
            {STATUS_LABEL[state.status]}
          </span>
          {incident.nearest_settlement && (
            <span>
              {formatDistance(incident.nearest_settlement.distance_km)} до {incident.nearest_settlement.name}
            </span>
          )}
        </span>
      </button>
    </li>
  );
});
