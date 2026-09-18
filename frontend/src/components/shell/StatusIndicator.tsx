"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import { useLiveStatus } from "@/lib/api/queries";
import type { LiveHealth } from "@/lib/api/types";
import { formatExact, formatRelative } from "@/lib/format";
import { useWorkspace } from "@/state/workspace";

import styles from "./shell.module.css";

const HEALTH_LABEL: Record<LiveHealth, string> = {
  live: "Онлайн",
  nrt: "С небольшой задержкой",
  stale: "Данные устарели",
  offline: "Нет связи",
};

const HEALTH_TONE: Record<LiveHealth, string> = {
  live: "var(--confirmed)",
  nrt: "var(--observation)",
  stale: "var(--incident-medium)",
  offline: "var(--danger)",
};

export function StatusIndicator() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const appMode = useWorkspace((state) => state.appMode);
  const live = useLiveStatus();
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const timer = window.setInterval(tick, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  if (pathname === "/analytics" && searchParams.get("tab") === "area") {
    return (
      <span className={styles.updated} role="status" title="Источник и версия фиксируются выбранным набором">
        <span className={styles.statusDot} style={{ background: "var(--observation)" }} />
        <span className={styles.updatedLabel}>Источник указан в наборе</span>
      </span>
    );
  }

  if (pathname !== "/") {
    return (
      <span className={styles.updated} role="status" title="Раздел использует фиксированный DemoFireRepository">
        <span className={styles.statusDot} style={{ background: "var(--text-tertiary)" }} />
        <span className={styles.updatedLabel}>Демоданные</span>
      </span>
    );
  }

  if (appMode === "replay") {
    return (
      <span className={styles.updated} role="status" title="Показан демонстрационный сценарий с фиксированными данными">
        <span className={styles.statusDot} style={{ background: "var(--text-tertiary)" }} />
        <span className={styles.updatedLabel}>Демоданные</span>
      </span>
    );
  }

  if (live.isPending) {
    return (
      <span className={styles.updated} role="status">
        <span className={styles.statusDot} data-state="loading" />
        <span className={styles.updatedLabel}>Загрузка…</span>
      </span>
    );
  }

  if (live.isError || !live.data) {
    return (
      <span className={styles.updated} role="status">
        <span className={styles.statusDot} data-state="error" />
        <span className={styles.updatedLabel}>Нет связи с сервером</span>
      </span>
    );
  }

  const status = live.data;
  const time = status.last_fetch_at;
  const detail = time && now ? `обновлено ${formatRelative(time, now)}` : !status.configured ? "источник не подключён" : undefined;
  const label = detail ? `${HEALTH_LABEL[status.status]} · ${detail}` : HEALTH_LABEL[status.status];
  const tooltip = time
    ? `Последняя загрузка: ${formatExact(time)}\nИсточник: ${status.source}`
    : status.configured
      ? (status.error ?? status.source)
      : `Источник ${status.source} пока не подключён. Настройку выполняет администратор.`;

  return (
    <span className={styles.updated} role="status" title={tooltip}>
      <span className={styles.statusDot} style={{ background: HEALTH_TONE[status.status] }} />
      <span className={styles.updatedLabel}>{label}</span>
    </span>
  );
}
