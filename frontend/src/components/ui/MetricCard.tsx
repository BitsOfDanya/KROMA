import type { ReactNode } from "react";

import { Card } from "./Card";
import styles from "./ui.module.css";

export function MetricCard({ label, value, description, icon, tone = "neutral" }: {
  label: string;
  value: ReactNode;
  description?: string;
  icon: ReactNode;
  tone?: "neutral" | "danger" | "positive" | "info";
}) {
  return (
    <Card className={styles.metricCard} data-tone={tone}>
      <div className={styles.metricHeading}>
        <span className={styles.metricIcon} aria-hidden="true">{icon}</span>
        <span>{label}</span>
      </div>
      <div className={styles.metricNumber}>{value}</div>
      {description && <p className={styles.metricDescription}>{description}</p>}
    </Card>
  );
}
