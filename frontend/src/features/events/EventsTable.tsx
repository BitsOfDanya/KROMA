"use client";

import { Activity, ArrowDown, ArrowUp, Flame, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusGlyph } from "@/components/ui/StatusPill";
import { useIncidents } from "@/lib/api/queries";
import type { IncidentSummary } from "@/lib/api/types";
import { formatArea, formatDistance, formatExact, formatRelative } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/labels";

import styles from "./events.module.css";

type SortKey = "id" | "status" | "region" | "first_detected_at" | "confidence" | "threat" | "priority" | "area_ha" | "nearest" | "updated_at";

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "id", label: "ID" },
  { key: "status", label: "Статус" },
  { key: "region", label: "Регион" },
  { key: "first_detected_at", label: "Обнаружен" },
  { key: "confidence", label: "Confidence", numeric: true },
  { key: "threat", label: "Threat", numeric: true },
  { key: "priority", label: "Priority", numeric: true },
  { key: "area_ha", label: "Площадь", numeric: true },
  { key: "nearest", label: "Ближайший НП" },
  { key: "updated_at", label: "Обновлён" },
];

function sortValue(item: IncidentSummary, key: SortKey): string | number {
  switch (key) {
    case "region":
      return `${item.region} ${item.district}`;
    case "nearest":
      return item.nearest_settlement?.distance_km ?? Number.POSITIVE_INFINITY;
    case "first_detected_at":
    case "updated_at":
      return new Date(item[key]).getTime();
    default:
      return item[key] as string | number;
  }
}

export function EventsTable({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const query = useIncidents();
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "priority", desc: true });

  const rows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("ru");
    const filtered = (query.data?.items ?? []).filter((item) =>
      !needle
        ? true
        : [item.id, item.district, item.region, item.nearest_settlement?.name ?? ""].some((value) =>
            value.toLocaleLowerCase("ru").includes(needle),
          ),
    );
    const sorted = [...filtered].sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);
      const compared = typeof av === "string" ? av.localeCompare(bv as string, "ru") : (av as number) - (bv as number);
      return sort.desc ? -compared : compared;
    });
    return sorted;
  }, [query.data, search, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((current) => (current.key === key ? { key, desc: !current.desc } : { key, desc: true }));

  const counts = query.data?.counts;

  return (
    <div className={styles.tableContent}>
      <PageHeader
        className={styles.eventsHeader}
        title="События"
        description="Оперативная очередь обнаруженных пожаров"
        meta={
          <div className={styles.stats}>
            <span className={styles.stat}>
              <span className={styles.statIcon}><Activity size={18} /></span>
              <span className={styles.statText}><strong>{counts?.active ?? "—"}</strong><small>Активных</small></span>
            </span>
            <span className={styles.stat} data-tone="critical">
              <span className={styles.statIcon}><Flame size={18} /></span>
              <span className={styles.statText}><strong>{counts?.critical ?? "—"}</strong><small>Критических</small></span>
            </span>
            <span className={styles.stat} data-tone="new">
              <span className={styles.statIcon}><Sparkles size={18} /></span>
              <span className={styles.statText}><strong>{counts?.new_24h ?? "—"}</strong><small>Новых за 24 ч</small></span>
            </span>
          </div>
        }
      />
      <Card className={styles.tableCard}>
        <div className={styles.toolbar}>
          <TextField
            className={styles.search}
            icon={<Search size={17} strokeWidth={1.8} />}
            type="search"
            placeholder="Поиск по ID, району, посёлку"
            aria-label="Поиск событий"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className={styles.tableWrap}>
          {query.isPending && (
            <div style={{ padding: 16, display: "grid", gap: 10 }}>
              {Array.from({ length: 8 }, (_, index) => (
                <Skeleton key={index} height={16} />
              ))}
            </div>
          )}
          {query.isError && <ErrorMessage error={query.error} onRetry={() => query.refetch()} retrying={query.isFetching} />}
          {query.data && rows.length === 0 && <StateMessage title="Ничего не найдено" detail="Измените запрос поиска." />}
          {rows.length > 0 && (
            <table className={styles.table}>
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th
                      key={column.key}
                      data-sortable="true"
                      onClick={() => toggleSort(column.key)}
                      style={column.numeric ? { textAlign: "right" } : undefined}
                    >
                      {column.label}
                      {sort.key === column.key &&
                        (sort.desc ? (
                          <ArrowDown size={11} className={styles.sortIcon} />
                        ) : (
                          <ArrowUp size={11} className={styles.sortIcon} />
                        ))}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={item.id} aria-selected={item.id === selectedId} onClick={() => onSelect(item.id)}>
                    <td className="mono">{item.id}</td>
                    <td>
                      <span className={styles.statusCell}>
                        <StatusGlyph status={item.status} />
                        {STATUS_LABEL[item.status]}
                      </span>
                    </td>
                    <td>
                      {item.region}
                      <div className={styles.cellMuted}>{item.district}</div>
                    </td>
                    <td title={formatExact(item.first_detected_at)}>{formatRelative(item.first_detected_at)}</td>
                    <td className={styles.numeric}>{item.confidence}</td>
                    <td className={styles.numeric}>{item.threat}</td>
                    <td className={styles.numeric}>
                      <span className={styles.priorityCell}>{item.priority}</span>
                    </td>
                    <td className={styles.numeric}>{formatArea(item.area_ha)}</td>
                    <td>
                      {item.nearest_settlement
                        ? `${item.nearest_settlement.name} · ${formatDistance(item.nearest_settlement.distance_km)}`
                        : "—"}
                    </td>
                    <td title={formatExact(item.updated_at)}>{formatRelative(item.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>
    </div>
  );
}
