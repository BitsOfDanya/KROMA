import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import type { EvidenceItem } from "@/lib/api/types";

import styles from "./incidents.module.css";

const STRENGTH = { weak: 1, moderate: 2, strong: 3 } as const;
const STRENGTH_LABEL = { weak: "слабый", moderate: "умеренный", strong: "сильный" } as const;

export function EvidenceList({ items }: { items: EvidenceItem[] }) {
  return (
    <ul className={styles.evidence}>
      {items.map((item) => (
        <li key={item.code} className={styles.evidenceItem}>
          <span className={styles.evidenceIcon} data-effect={item.effect}>
            {item.effect === "raises" ? (
              <ArrowUpRight size={14} strokeWidth={2} aria-label="повышает приоритет" />
            ) : (
              <ArrowDownRight size={14} strokeWidth={2} aria-label="понижает приоритет" />
            )}
          </span>
          <span>
            <div className={styles.evidenceLabel}>{item.label}</div>
            <div className={styles.evidenceDetail}>{item.detail}</div>
          </span>
          <span className={styles.strength} title={`Вклад: ${STRENGTH_LABEL[item.strength]}`}>
            {[1, 2, 3].map((level) => (
              <span key={level} data-on={level <= STRENGTH[item.strength]} />
            ))}
          </span>
        </li>
      ))}
    </ul>
  );
}
