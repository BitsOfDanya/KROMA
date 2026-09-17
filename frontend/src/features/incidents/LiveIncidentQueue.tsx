"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { SeverityMark, StatusGlyph } from "@/components/ui/StatusPill";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { Skeleton } from "@/components/ui/Skeleton";
import overviewStyles from "@/features/overview/overview.module.css";
import { useLiveIncidents, useLiveStatus } from "@/lib/api/queries";
import type { FeatureCollection, IncidentStatus, Severity } from "@/lib/api/types";
import { formatExact, formatRelative } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/labels";
import { useWorkspace } from "@/state/workspace";

import styles from "./incidents.module.css";

interface LiveIncidentProperties {
  id: string;
  status: IncidentStatus;
  severity: Severity;
  priority: number;
  detection_count: number;
  frp_mw: number;
  sources: string;
  updated: number;
}

export function LiveIncidentQueue() {
  const query = useLiveIncidents(null, true);
  const status = useLiveStatus();
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const closePanel = useWorkspace((state) => state.closePanel);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const rows = useMemo(() => {
    const features = (query.data as FeatureCollection<LiveIncidentProperties> | undefined)?.features ?? [];
    return [...features].sort((a, b) => b.properties.priority - a.properties.priority);
  }, [query.data]);

  const critical = rows.filter((item) => item.properties.severity === "critical").length;
  const confirmed = rows.filter((item) => item.properties.status === "confirmed").length;

  return (
    <section className={overviewStyles.panel} aria-labelledby="queue-title">
      <header className={overviewStyles.panelHeader}>
        <h2 id="queue-title" className={overviewStyles.panelTitle}>
          События
        </h2>
        <span style={{ flex: 1 }} />
        <IconButton label="Закрыть панель" size="sm" showTooltip={false} icon={<X size={15} />} onClick={closePanel} />
      </header>
      <div className={styles.summary}>
        <div className={styles.summaryCell}>
          <span className={styles.summaryValue}>{query.data ? rows.length : "—"}</span>
          <span className={styles.summaryLabel}>Кластеров</span>
        </div>
        <div className={styles.summaryCell}>
          <span className={styles.summaryValue} data-tone={critical ? "critical" : undefined}>
            {query.data ? critical : "—"}
          </span>
          <span className={styles.summaryLabel}>Критические</span>
        </div>
        <div className={styles.summaryCell}>
          <span className={styles.summaryValue}>{query.data ? confirmed : "—"}</span>
          <span className={styles.summaryLabel}>Подтверждённые</span>
        </div>
      </div>
      <div className={overviewStyles.panelBody}>
        {status.data && !status.data.configured && (
          <StateMessage
            title="Источник не настроен"
            detail="Задайте NASA_FIRMS_API_KEY на backend, чтобы получать актуальные детекции."
          />
        )}
        {status.data?.configured && query.isPending && (
          <div aria-busy="true" aria-label="Загрузка событий">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className={styles.skeletonRow}>
                <Skeleton height={36} />
                <div style={{ display: "grid", gap: 6, alignContent: "center" }}>
                  <Skeleton width="70%" />
                  <Skeleton width="45%" height={10} />
                </div>
              </div>
            ))}
          </div>
        )}
        {query.isError && <ErrorMessage error={query.error} onRetry={() => query.refetch()} retrying={query.isFetching} />}
        {status.data?.configured && query.data && rows.length === 0 && (
          <StateMessage title="Нет активных детекций" detail="За окно ретенции ничего не обнаружено." />
        )}
        {rows.length > 0 && (
          <ul className={styles.list}>
            {rows.map((feature) => {
              const p = feature.properties;
              return (
                <li key={p.id}>
                  <button type="button" className={styles.item} aria-current={p.id === selectedId}>
                    <span className={styles.priority} title={`Priority ${p.priority}`}>
                      <span className={styles.priorityValue}>{p.priority}</span>
                      <SeverityMark severity={p.severity} />
                    </span>
                    <span className={styles.itemTitle}>
                      <span className="mono">{p.id}</span>
                    </span>
                    <span className={styles.itemSide}>
                      <span />
                      <span title={formatExact(p.updated * 1000)}>{formatRelative(p.updated * 1000, now)}</span>
                    </span>
                    <span className={styles.itemMeta}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                        <StatusGlyph status={p.status} />
                        {STATUS_LABEL[p.status]}
                      </span>
                      <span>
                        {p.detection_count} детекций · {Math.round(p.frp_mw)} МВт
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
