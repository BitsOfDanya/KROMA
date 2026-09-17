"use client";

import { X } from "lucide-react";

import { IconButton } from "@/components/ui/IconButton";
import overviewStyles from "@/features/overview/overview.module.css";
import uiStyles from "@/components/ui/ui.module.css";
import { StatusGlyph } from "@/components/ui/StatusPill";
import { useOverview } from "@/lib/api/queries";
import type { IncidentStatus } from "@/lib/api/types";
import { STATUS_LABEL } from "@/lib/labels";
import { useWorkspace } from "@/state/workspace";

import styles from "./layers.module.css";

const STATUSES: IncidentStatus[] = ["confirmed", "suspected", "monitoring", "localized"];

export function FiltersPanel() {
  const overview = useOverview();
  const regionId = useWorkspace((state) => state.regionId);
  const setRegion = useWorkspace((state) => state.setRegion);
  const statusFilter = useWorkspace((state) => state.statusFilter);
  const toggleStatus = useWorkspace((state) => state.toggleStatus);
  const priorityMin = useWorkspace((state) => state.priorityMin);
  const setPriorityMin = useWorkspace((state) => state.setPriorityMin);
  const resetFilters = useWorkspace((state) => state.resetFilters);
  const closePanel = useWorkspace((state) => state.closePanel);
  const active = statusFilter.length > 0 || priorityMin > 0 || regionId !== null;

  return (
    <section className={overviewStyles.panel} aria-labelledby="filters-title">
      <header className={overviewStyles.panelHeader}>
        <h2 id="filters-title" className={overviewStyles.panelTitle}>
          Фильтры
        </h2>
        <span style={{ flex: 1 }} />
        {active && (
          <button type="button" className={uiStyles.textButton} data-variant="quiet" onClick={resetFilters}>
            Сбросить
          </button>
        )}
        <IconButton label="Закрыть панель" size="sm" showTooltip={false} icon={<X size={15} />} onClick={closePanel} />
      </header>
      <div className={overviewStyles.panelBody}>
        <div className={styles.group}>
          <h3 className={styles.groupTitle}>Регион</h3>
          <div className={styles.field}>
            <select
              className={styles.regionSelect}
              aria-label="Регион"
              value={regionId ?? ""}
              onChange={(event) => setRegion(event.target.value || null)}
            >
              <option value="">Все регионы</option>
              {overview.data?.regions.map((region) => (
                <option key={region.id} value={region.id}>
                  {region.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className={styles.group}>
          <h3 className={styles.groupTitle}>Статус</h3>
          <div className={styles.checks}>
            {STATUSES.map((status) => (
              <label key={status} className={styles.check}>
                <input type="checkbox" checked={statusFilter.includes(status)} onChange={() => toggleStatus(status)} />
                <StatusGlyph status={status} />
                {STATUS_LABEL[status]}
              </label>
            ))}
          </div>
        </div>
        <div className={styles.group}>
          <h3 className={styles.groupTitle}>Приоритет</h3>
          <div className={styles.field}>
            <label className={styles.fieldLabel} htmlFor="priority-min">
              Не ниже
              <output htmlFor="priority-min">{priorityMin}</output>
            </label>
            <input
              id="priority-min"
              className={styles.range}
              type="range"
              min={0}
              max={95}
              step={5}
              value={priorityMin}
              onChange={(event) => setPriorityMin(Number(event.target.value))}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
