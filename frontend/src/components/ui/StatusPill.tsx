import type { IncidentStatus, Severity } from "@/lib/api/types";
import { SEVERITY_LABEL, STATUS_LABEL } from "@/lib/labels";

import styles from "./ui.module.css";

const STATUS_COLOR: Record<IncidentStatus, string> = {
  suspected: "var(--incident-medium)",
  confirmed: "var(--confirmed)",
  monitoring: "var(--observation)",
  localized: "var(--incident-localized)",
};

export function StatusGlyph({ status, size = 8 }: { status: IncidentStatus; size?: number }) {
  const color = STATUS_COLOR[status];
  const r = size / 2;
  return (
    <svg className={styles.pillGlyph} width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {status === "confirmed" && <circle cx={r} cy={r} r={r - 0.5} fill={color} />}
      {status === "suspected" && <circle cx={r} cy={r} r={r - 1} fill="none" stroke={color} strokeWidth="1.4" />}
      {status === "monitoring" && (
        <>
          <circle cx={r} cy={r} r={r - 1} fill="none" stroke={color} strokeWidth="1.4" />
          <circle cx={r} cy={r} r={r / 2.6} fill={color} />
        </>
      )}
      {status === "localized" && <rect x="0.5" y={r - 1} width={size - 1} height="2" rx="1" fill={color} />}
    </svg>
  );
}

export function StatusPill({ status }: { status: IncidentStatus }) {
  return (
    <span className={styles.pill}>
      <StatusGlyph status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}

const SEVERITY_LEVEL: Record<Severity, number> = { low: 1, medium: 2, high: 3, critical: 4 };

export function SeverityMark({ severity }: { severity: Severity }) {
  const level = SEVERITY_LEVEL[severity];
  return (
    <span className={styles.severity} role="img" aria-label={`Уровень: ${SEVERITY_LABEL[severity]}`} title={SEVERITY_LABEL[severity]}>
      {[1, 2, 3, 4].map((bar) => (
        <span key={bar} style={bar <= level ? { background: `var(--incident-${severity})` } : undefined} />
      ))}
    </span>
  );
}
