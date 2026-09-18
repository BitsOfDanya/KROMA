import type { IncidentState } from "@/lib/replay";

import { AnimatedNumber } from "./AnimatedNumber";
import styles from "./incidents.module.css";

function barColor(value: number) {
  if (value >= 85) return "var(--incident-critical)";
  if (value >= 65) return "var(--incident-high)";
  if (value >= 40) return "var(--incident-medium)";
  return "var(--incident-low)";
}

const METRICS = [
  { key: "confidence", label: "Достоверность", hint: "Достоверность того, что это лесной пожар, от 0 до 100" },
  { key: "threat", label: "Угроза", hint: "Угроза объектам и населению, от 0 до 100" },
  { key: "priority", label: "Приоритет", hint: "Итоговый приоритет реагирования, от 0 до 100" },
] as const;

export function PriorityMetrics({ state }: { state: IncidentState }) {
  return (
    <div className={styles.metrics}>
      {METRICS.map((metric) => {
        const value = state[metric.key];
        const color = metric.key === "confidence" ? "var(--confirmed)" : barColor(value);
        return (
          <div key={metric.key} className={styles.metric} title={metric.hint}>
            <div className={styles.metricLabel}>{metric.label}</div>
            <span className={styles.metricValue} aria-label={`${metric.label}: ${value} из 100`}>
              <AnimatedNumber value={value} />
            </span>
            <div className={styles.metricBar} aria-hidden="true">
              <span style={{ width: `${value}%`, background: color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
