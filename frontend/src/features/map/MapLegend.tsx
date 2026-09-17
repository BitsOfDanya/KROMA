"use client";

import { useWorkspace } from "@/state/workspace";

import styles from "./map.module.css";

function IncidentGlyph({ kind }: { kind: "suspected" | "confirmed" | "critical" }) {
  const color = kind === "critical" ? "var(--incident-critical)" : kind === "confirmed" ? "var(--incident-high)" : "var(--incident-medium)";
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      {kind === "suspected" && (
        <>
          <circle cx="11" cy="11" r="6" fill="none" stroke={color} strokeWidth="1.5" />
          <circle cx="11" cy="11" r="1.8" fill={color} />
        </>
      )}
      {kind !== "suspected" && (
        <>
          <circle cx="11" cy="11" r="7" fill="none" stroke={color} strokeWidth="1" opacity="0.55" />
          <circle cx="11" cy="11" r="4" fill={color} />
        </>
      )}
      {kind === "critical" && <circle cx="11" cy="11" r="10" fill="none" stroke={color} strokeWidth="1" opacity="0.45" />}
    </svg>
  );
}

function Swatch({ color, opacity = 1, dashed, line }: { color: string; opacity?: number; dashed?: boolean; line?: boolean }) {
  return (
    <svg width="22" height="12" viewBox="0 0 22 12" aria-hidden="true">
      {line ? (
        <line x1="1" y1="6" x2="21" y2="6" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeDasharray={dashed ? "2 2" : undefined} />
      ) : (
        <rect x="1" y="1" width="20" height="10" rx="2" fill={color} fillOpacity={opacity} stroke={color} strokeOpacity={0.8} strokeDasharray={dashed ? "2 2" : undefined} />
      )}
    </svg>
  );
}

export function MapLegend() {
  const evidenceMode = useWorkspace((state) => state.evidenceMode);
  const layers = useWorkspace((state) => state.layers);
  const selected = useWorkspace((state) => state.selectedIncidentId);
  const isReplay = useWorkspace((state) => state.appMode) === "replay";

  return (
    <section className={styles.legend} aria-label="Легенда карты">
      {evidenceMode === "events" ? (
        <>
          <h3 className={styles.legendTitle}>События</h3>
          <div className={styles.legendRows}>
            <div className={styles.legendRow}><IncidentGlyph kind="critical" />Критический</div>
            <div className={styles.legendRow}><IncidentGlyph kind="confirmed" />Подтверждён</div>
            <div className={styles.legendRow}><IncidentGlyph kind="suspected" />Предварительный</div>
            {isReplay && layers.activeFront && <div className={styles.legendRow}><Swatch color="var(--incident-critical)" line />Активная кромка</div>}
          </div>
          {isReplay && selected && (layers.forecastP50 || layers.forecastP80 || layers.forecastP95) && (
            <>
              <h3 className={styles.legendTitle}>Прогноз · 24 ч</h3>
              <div className={styles.legendRows}>
                {layers.forecastP50 && <div className={styles.legendRow}><Swatch color="var(--forecast-50)" opacity={0.35} />P50 — наиболее вероятно</div>}
                {layers.forecastP80 && <div className={styles.legendRow}><Swatch color="var(--forecast-80)" opacity={0.22} />P80</div>}
                {layers.forecastP95 && <div className={styles.legendRow}><Swatch color="var(--forecast-95)" opacity={0.12} dashed />P95 — неопределённость</div>}
              </div>
            </>
          )}
        </>
      ) : (
        <>
          <h3 className={styles.legendTitle}>Спутниковые детекции</h3>
          <div className={styles.legendRows}>
            <div className={styles.legendRow}><Swatch color="var(--observation-fresh)" line />Свежие, до 6 ч</div>
            <div className={styles.legendRow}><Swatch color="var(--observation)" line />Более ранние</div>
            <div className={styles.legendRow}>
              <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
                <circle cx="11" cy="11" r="9" fill="var(--observation)" fillOpacity="0.14" stroke="var(--observation)" strokeOpacity="0.65" />
              </svg>
              Кластер детекций
            </div>
          </div>
        </>
      )}
      {isReplay && (layers.burnScars || layers.thermalMemory || layers.infrastructure) && <h3 className={styles.legendTitle}>Контекст</h3>}
      {isReplay && (
        <div className={styles.legendRows}>
          {layers.burnScars && <div className={styles.legendRow}><Swatch color="var(--burn-scar)" opacity={0.35} />Гарь</div>}
          {layers.thermalMemory && (
            <div className={styles.legendRow}>
              <svg width="22" height="14" viewBox="0 0 22 14" aria-hidden="true">
                <path d="M11 1.5 L16.5 7 L11 12.5 L5.5 7 Z" fill="none" stroke="var(--thermal-source)" strokeWidth="1.4" />
              </svg>
              Постоянный тепловой источник
            </div>
          )}
          {layers.infrastructure && <div className={styles.legendRow}><Swatch color="var(--infrastructure)" line dashed />ЛЭП / инфраструктура</div>}
        </div>
      )}
    </section>
  );
}
