"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { incidentStateAt } from "@/lib/replay";
import overviewStyles from "@/features/overview/overview.module.css";
import { useWorkspace, type QueueFilter } from "@/state/workspace";

import { IncidentListItem } from "./IncidentListItem";
import styles from "./incidents.module.css";
import { useFilteredIncidents } from "./useFilteredIncidents";

export function IncidentQueue() {
  const query = useFilteredIncidents();
  const cursor = useWorkspace((state) => state.cursor);
  const selectedId = useWorkspace((state) => state.selectedIncidentId);
  const selectIncident = useWorkspace((state) => state.selectIncident);
  const filter = useWorkspace((state) => state.queueFilter);
  const setFilter = useWorkspace((state) => state.setQueueFilter);
  const closePanel = useWorkspace((state) => state.closePanel);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const rows = useMemo(() => {
    const mapped = query.items.map((incident) => ({ incident, state: incidentStateAt(incident, cursor) }));
    const active = mapped.filter(({ incident }) => incident.status !== "localized" || filter === "all");
    const filtered = active.filter(({ state }) => {
      if (filter === "critical") return state.severity === "critical";
      if (filter === "confirmed") return state.status === "confirmed";
      if (filter === "monitoring") return state.status === "monitoring" || state.status === "suspected";
      return true;
    });
    return filtered.sort((a, b) => Number(b.state.visible) - Number(a.state.visible) || b.state.priority - a.state.priority);
  }, [query.items, cursor, filter]);

  const counts = useMemo(() => {
    const states = query.items.map((incident) => ({ incident, state: incidentStateAt(incident, cursor) }));
    const active = states.filter(({ state, incident }) => state.visible && incident.status !== "localized");
    return {
      active: active.length,
      critical: active.filter(({ state }) => state.severity === "critical").length,
      fresh: active.filter(({ incident }) => incident.is_new).length,
      confirmed: active.filter(({ state }) => state.status === "confirmed").length,
      watch: active.filter(({ state }) => state.status === "monitoring" || state.status === "suspected").length,
    };
  }, [query.items, cursor]);

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
          <span className={styles.summaryValue}>{query.data ? counts.active : "—"}</span>
          <span className={styles.summaryLabel}>Активные</span>
        </div>
        <div className={styles.summaryCell}>
          <span className={styles.summaryValue} data-tone={counts.critical ? "critical" : undefined}>
            {query.data ? counts.critical : "—"}
          </span>
          <span className={styles.summaryLabel}>Критические</span>
        </div>
        <div className={styles.summaryCell}>
          <span className={styles.summaryValue}>{query.data ? counts.fresh : "—"}</span>
          <span className={styles.summaryLabel}>Новые за 24 ч</span>
        </div>
      </div>
      <div className={styles.filters}>
        <SegmentedControl<QueueFilter>
          label="Фильтр очереди"
          size="sm"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "Все" },
            { value: "critical", label: "Критические", count: counts.critical },
            { value: "confirmed", label: "Подтверждённые", count: counts.confirmed },
            { value: "monitoring", label: "Наблюдение", count: counts.watch },
          ]}
        />
      </div>
      <div className={overviewStyles.panelBody}>
        {query.isPending && (
          <div aria-busy="true" aria-label="Загрузка событий">
            {Array.from({ length: 6 }, (_, index) => (
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
        {query.data && rows.length === 0 && (
          <StateMessage title="Нет событий" detail="По выбранным фильтрам активных событий нет." />
        )}
        {rows.length > 0 && (
          <ul className={styles.list}>
            {rows.map(({ incident, state }) => (
              <IncidentListItem
                key={incident.id}
                incident={incident}
                state={state}
                now={now}
                selected={incident.id === selectedId}
                onSelect={selectIncident}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
