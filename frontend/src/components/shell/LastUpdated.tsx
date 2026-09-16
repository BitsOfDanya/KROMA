"use client";

import { useEffect, useState } from "react";

import { useOverview } from "@/lib/api/queries";
import { formatExact, formatRelative } from "@/lib/format";

import styles from "./shell.module.css";

export function LastUpdated() {
  const overview = useOverview();
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const timer = window.setInterval(tick, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const state = overview.isError ? "error" : overview.data ? "ok" : "loading";
  const time = overview.data?.last_observation_at ?? overview.data?.reference_time;
  const label =
    state === "error" ? "API недоступен" : time && now ? `Обновлено ${formatRelative(time, now)}` : "Загрузка…";

  return (
    <span className={styles.updated} title={time ? `Последнее наблюдение: ${formatExact(time)}` : undefined} role="status">
      <span className={styles.statusDot} data-state={state} />
      <span className={styles.updatedLabel}>{label}</span>
    </span>
  );
}
