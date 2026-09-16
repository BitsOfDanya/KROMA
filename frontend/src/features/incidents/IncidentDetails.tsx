"use client";

import { Building2, Cable, Home, Landmark, Route, Satellite, Trees } from "lucide-react";
import { useEffect, useState } from "react";

import type { IncidentDetail, RiskObjectKind } from "@/lib/api/types";
import {
  compassPoint,
  formatArea,
  formatDistance,
  formatExact,
  formatRelative,
  formatSpeed,
  pluralize,
} from "@/lib/format";
import { FORECAST_LABEL } from "@/lib/labels";
import type { IncidentState } from "@/lib/replay";

import { EvidenceList } from "./EvidenceList";
import styles from "./incidents.module.css";
import { PriorityMetrics } from "./PriorityMetrics";

const RISK_ICON: Record<RiskObjectKind, typeof Home> = {
  settlement: Home,
  power_line: Cable,
  road: Route,
  infrastructure: Building2,
  protected_area: Trees,
};

const FORECAST_COLOR = { p50: "var(--forecast-50)", p80: "var(--forecast-80)", p95: "var(--forecast-95)" } as const;

export function IncidentDetails({ detail, state }: { detail: IncidentDetail; state: IncidentState }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const passes = detail.next_passes.filter((item) => new Date(item.overpass_at).getTime() > now).slice(0, 4);
  const optical = passes.find((item) => item.kind === "optical");

  return (
    <>
      <PriorityMetrics state={state} />

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Почему такой приоритет</h3>
        <EvidenceList items={detail.evidence} />
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>
          Сейчас
          {state.observed_at && (
            <span className={styles.sectionHint} title={formatExact(state.observed_at)}>
              по наблюдению {formatRelative(state.observed_at, now)}
            </span>
          )}
        </h3>
        <dl className={styles.facts}>
          <div>
            <dt>Площадь, оценка</dt>
            <dd>{formatArea(state.area_ha)}</dd>
          </div>
          <div>
            <dt>FRP</dt>
            <dd>
              {Math.round(state.frp_mw)} <small>МВт</small>
            </dd>
          </div>
          <div>
            <dt>Направление</dt>
            <dd>
              {compassPoint(detail.spread.direction_deg)} <small>{Math.round(detail.spread.direction_deg)}°</small>
            </dd>
          </div>
          <div>
            <dt>Скорость кромки</dt>
            <dd>{formatSpeed(detail.spread.speed_m_per_h)}</dd>
          </div>
          <div>
            <dt>Ветер</dt>
            <dd>
              {compassPoint(detail.spread.wind_from_deg)} <small>{detail.spread.wind_speed_ms.toLocaleString("ru-RU")} м/с</small>
            </dd>
          </div>
          <div>
            <dt>Наблюдения</dt>
            <dd>{pluralize(state.observation_count, ["пиксель", "пикселя", "пикселей"])}</dd>
          </div>
        </dl>
      </section>

      {detail.exposures.length > 0 && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            Объекты риска <span className={styles.sectionHint}>расстояние до кромки</span>
          </h3>
          <ul className={styles.rows}>
            {detail.exposures.slice(0, 6).map((item) => {
              const Icon = RISK_ICON[item.kind] ?? Landmark;
              return (
                <li key={item.object_id} className={styles.row}>
                  <Icon size={14} strokeWidth={1.75} className={styles.rowIcon} aria-hidden="true" />
                  <span style={{ minWidth: 0 }}>
                    <div className={styles.rowName}>{item.name}</div>
                    <div className={styles.rowSub}>{item.subtitle}</div>
                  </span>
                  <span className={styles.rowValue}>
                    {item.distance_km === 0 ? "в периметре" : formatDistance(item.distance_km)}
                    {item.forecast_level && (
                      <span
                        className={styles.forecastTag}
                        style={{ color: FORECAST_COLOR[item.forecast_level] }}
                        title={`Попадает в прогнозную зону ${FORECAST_LABEL[item.forecast_level]}`}
                      >
                        {FORECAST_LABEL[item.forecast_level]}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {passes.length > 0 && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            Следующие пролёты
            {optical?.cloud_probability != null && (
              <span className={styles.sectionHint}>облачность {optical.satellite}: {optical.cloud_probability}%</span>
            )}
          </h3>
          <ul className={styles.rows}>
            {passes.map((item) => (
              <li key={item.id} className={styles.row}>
                <Satellite size={14} strokeWidth={1.75} className={styles.rowIcon} aria-hidden="true" />
                <span style={{ minWidth: 0 }}>
                  <div className={styles.rowName}>
                    {item.satellite} <span style={{ color: "var(--text-tertiary)" }}>{item.instrument}</span>
                  </div>
                  <div className={styles.rowSub}>
                    {item.kind === "thermal" ? "Тепловой" : "Оптический"} · {item.resolution_m} м
                    {item.cloud_probability != null && ` · облака ${item.cloud_probability}%`}
                  </div>
                </span>
                <span className={styles.rowValue} title={formatExact(item.overpass_at)}>
                  {formatRelative(item.overpass_at, now)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
