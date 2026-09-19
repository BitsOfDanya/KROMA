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
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!fetching) {
      setStep(done ? STEPS.length - 1 : 0);
      return;
    }
    setStep(0);
    const timers = [
      window.setTimeout(() => setStep(1), 280),
      window.setTimeout(() => setStep(2), 700),
      window.setTimeout(() => setStep(3), 1200),
    ];
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [fetching, done]);

  if (!fetching && !done) return null;

  const active = fetching ? Math.min(step, STEPS.length - 2) : STEPS.length - 1;

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
