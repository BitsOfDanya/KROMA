"use client";

import { useEffect, useState } from "react";

import styles from "./analysis.module.css";

const STEPS = [
  "Подготовка данных",
  "Активное горение",
  "Оценка гари",
  "Расчёт площадей",
  "Готово",
] as const;

export function AnalysisProgress({
  fetching,
  done,
}: {
  fetching: boolean;
  done: boolean;
}) {
  const [animStep, setAnimStep] = useState(0);

  useEffect(() => {
    if (!fetching) return;
    const timers = [
      window.setTimeout(() => setAnimStep(0), 0),
      window.setTimeout(() => setAnimStep(1), 280),
      window.setTimeout(() => setAnimStep(2), 700),
      window.setTimeout(() => setAnimStep(3), 1200),
    ];
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [fetching]);

  if (!fetching && !done) return null;

  const active = fetching ? Math.min(animStep, STEPS.length - 2) : STEPS.length - 1;

  return (
    <ol className={styles.progress} aria-label="Ход анализа">
      {STEPS.map((label, index) => {
        const state = index < active ? "done" : index === active ? "active" : "todo";
        return (
          <li key={label} data-state={state}>
            <span className={styles.progressDot} />
            <span>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
