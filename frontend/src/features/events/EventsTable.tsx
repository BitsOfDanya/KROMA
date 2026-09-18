"use client";

import { Activity, ArrowDown, ArrowUp, Flame, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { MetricCard } from "@/components/ui/MetricCard";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { useIncidents } from "@/lib/api/queries";
import type { IncidentSummary } from "@/lib/api/types";
import { formatArea, formatDistance, formatExact, formatRelative } from "@/lib/format";

import styles from "./events.module.css";

type SortKey = "id" | "status" | "region" | "first_detected_at" | "confidence" | "threat" | "priority" | "area_ha" | "nearest" | "updated_at";

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: "id", label: "Событие" },
  { key: "status", label: "Статус" },
  { key: "region", label: "Регион" },
  { key: "first_detected_at", label: "Обнаружен" },
  { key: "confidence", label: "Достоверность", numeric: true },
  { key: "threat", label: "Угроза", numeric: true },
  { key: "priority", label: "Приоритет", numeric: true },
  { key: "area_ha", label: "Площадь", numeric: true },
  { key: "nearest", label: "Ближайший посёлок" },
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
        title="События под наблюдением"
        description="Все события в одном месте. Выберите пожар, чтобы увидеть подробности."
      />
      <div className={styles.stats}>
        <MetricCard label="Активные события" value={counts?.active ?? "—"} description="Сейчас под наблюдением" icon={<Activity size={20} />} />
        <MetricCard label="Критические" value={counts?.critical ?? "—"} description="Требуют внимания в первую очередь" icon={<Flame size={20} />} tone="danger" />
        <MetricCard label="Новые за сутки" value={counts?.new_24h ?? "—"} description="Обнаружены за последние 24 часа" icon={<Sparkles size={20} />} tone="positive" />
      </div>
      <Card className={styles.tableCard}>
        <div className={styles.toolbar}>
          <div className={styles.tableHeading}>
            <h2>Все события <span>{query.data ? rows.length : "—"}</span></h2>
            <p>Оценки достоверности, угрозы и приоритета — от 0 до 100</p>
          </div>
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
                      aria-sort={sort.key === column.key ? (sort.desc ? "descending" : "ascending") : "none"}
                      style={column.numeric ? { textAlign: "right" } : undefined}
                    >
                      <button type="button" className={styles.sortButton} onClick={() => toggleSort(column.key)}>
                        {column.label}
                        {sort.key === column.key &&
                          (sort.desc ? (
                            <ArrowDown size={11} className={styles.sortIcon} />
                          ) : (
                            <ArrowUp size={11} className={styles.sortIcon} />
                          ))}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr key={item.id} aria-selected={item.id === selectedId} onClick={() => onSelect(item.id)}>
                    <td><button type="button" className={styles.eventLink} aria-label={`Открыть событие ${item.id}`} onClick={(event) => { event.stopPropagation(); onSelect(item.id); }}>{item.id}</button></td>
                    <td>
                      <StatusPill status={item.status} />
                    </td>
                    <td>
                      {item.region}
                      <div className={styles.cellMuted}>{item.district}</div>
                    </td>
                    <td title={formatExact(item.first_detected_at)}>{formatRelative(item.first_detected_at)}</td>
                    <td className={styles.numeric}>{item.confidence}</td>
                    <td className={styles.numeric}>{item.threat}</td>
                    <td className={styles.numeric}>
                      <span className={styles.priorityCell} data-level={item.priority >= 85 ? "high" : item.priority >= 65 ? "medium" : "low"}>{item.priority}</span>
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
