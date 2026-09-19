"use client";

import styles from "./analysis.module.css";

export function AnalysisProgress({
  fetching,
  done,
}: {
  fetching: boolean;
  done: boolean;
}) {
  if (!fetching && !done) return null;
  return (
    <ol className={styles.progress} aria-label="Ход анализа" aria-live="polite">
      <li data-state={fetching ? "active" : "done"}>
        <span className={styles.progressDot} />
        <span>
          {fetching
            ? "Выбор prepared scenes и расчёт пересечений…"
            : "Анализ готов"}
        </span>
      </li>
    </ol>
  );
}
