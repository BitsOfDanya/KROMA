"use client";

import { useRef, useState } from "react";

import { formatArea, formatDateLong, formatPercent } from "@/lib/format";
import type { BurnScar } from "@/lib/api/types";

import { CompareMap } from "./CompareMap";
import styles from "./analytics.module.css";

export function BurnScarCompare({ scar }: { scar: BurnScar }) {
  const [split, setSplit] = useState(50);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const setFromClientX = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return;
    const ratio = Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100));
    setSplit(ratio);
  };

  const low = scar.zones.find((zone) => zone.severity === "low")?.area_ha ?? 0;
  const moderate = scar.zones.find((zone) => zone.severity === "moderate")?.area_ha ?? 0;
  const high = scar.zones.find((zone) => zone.severity === "high")?.area_ha ?? 0;

  return (
    <div className={styles.compareRow}>
      <div>
        <div
          ref={trackRef}
          style={{ position: "relative", aspectRatio: "4 / 3", borderRadius: 8, overflow: "hidden", border: "1px solid var(--border)" }}
          onPointerDown={(event) => {
            dragging.current = true;
            event.currentTarget.setPointerCapture(event.pointerId);
            setFromClientX(event.clientX);
          }}
          onPointerMove={(event) => dragging.current && setFromClientX(event.clientX)}
          onPointerUp={() => {
            dragging.current = false;
          }}
        >
          <CompareMap scar={scar} variant="before" />
          <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 0 0 ${split}%)` }}>
            <CompareMap scar={scar} variant="after" />
          </div>
          <div
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${split}%`,
              width: 2,
              background: "#f4f1ea",
              cursor: "ew-resize",
              boxShadow: "0 0 0 1px rgba(0,0,0,0.35)",
            }}
          />
          <span
            style={{
              position: "absolute",
              left: 8,
              bottom: 8,
              fontSize: 10.5,
              fontWeight: 650,
              color: "#f4f1ea",
              padding: "3px 6px",
              borderRadius: 4,
              background: "rgba(0,0,0,0.45)",
              whiteSpace: "nowrap",
            }}
          >
            ДО · {scar.before.satellite}
          </span>
          <span
            style={{
              position: "absolute",
              right: 8,
              bottom: 8,
              fontSize: 10.5,
              fontWeight: 650,
              color: "#f4f1ea",
              padding: "3px 6px",
              borderRadius: 4,
              background: "rgba(0,0,0,0.45)",
              whiteSpace: "nowrap",
            }}
          >
            ПОСЛЕ · оценка выгорания
          </span>
        </div>
        <p style={{ marginTop: 8, fontSize: 11.5, color: "var(--text-tertiary)" }}>
          {scar.before.satellite} {formatDateLong(scar.before.acquired_on)} · облачность {scar.before.cloud_cover_pct}% — 
          {" "}{scar.after.satellite} {formatDateLong(scar.after.acquired_on)} · облачность {scar.after.cloud_cover_pct}%
        </p>
      </div>
      <div className={styles.compareStats}>
        <div className={styles.compareStat}>
          <div className={styles.compareStatLabel}>Выгоревшая площадь</div>
          <div className={styles.compareStatValue}>{formatArea(scar.area_ha)}</div>
        </div>
        <div className={styles.compareStat} style={{ borderColor: "color-mix(in srgb, var(--burn-low) 45%, var(--border))" }}>
          <div className={styles.compareStatLabel} style={{ color: "var(--burn-low)" }}>Низкая severity</div>
          <div className={styles.compareStatValue}>{formatArea(low)}</div>
        </div>
        <div className={styles.compareStat} style={{ borderColor: "color-mix(in srgb, var(--burn-moderate) 45%, var(--border))" }}>
          <div className={styles.compareStatLabel} style={{ color: "var(--burn-moderate)" }}>Средняя severity</div>
          <div className={styles.compareStatValue}>{formatArea(moderate)}</div>
        </div>
        <div className={styles.compareStat} style={{ borderColor: "color-mix(in srgb, var(--burn-high) 45%, var(--border))" }}>
          <div className={styles.compareStatLabel} style={{ color: "var(--burn-high)" }}>Высокая severity</div>
          <div className={styles.compareStatValue}>{formatArea(high)}</div>
        </div>
        <div className={styles.compareStat}>
          <div className={styles.compareStatLabel}>Средний dNBR</div>
          <div className={styles.compareStatValue}>{scar.dnbr_mean.toFixed(2)}</div>
        </div>
        <div className={styles.compareStat}>
          <div className={styles.compareStatLabel}>Доля высокой severity</div>
          <div className={styles.compareStatValue}>{formatPercent(high / scar.area_ha)}</div>
        </div>
      </div>
    </div>
  );
}
