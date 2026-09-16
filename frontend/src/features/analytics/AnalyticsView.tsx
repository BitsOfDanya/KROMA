"use client";

import { X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAnalytics, useBurnScar, useOverview } from "@/lib/api/queries";
import { formatArea, formatDateLong, formatDuration, formatInteger, formatPercent } from "@/lib/format";

import styles from "./analytics.module.css";
import { BurnScarCompare } from "./BurnScarCompare";
import { TrendChart } from "./TrendChart";

const SEVERITY_COLOR = { low: "var(--burn-low)", moderate: "var(--burn-moderate)", high: "var(--burn-high)" } as const;

function useRangeParams() {
  const searchParams = useSearchParams();
  return useMemo(() => {
    const now = new Date();
    const defaultFrom = new Date(now.getTime() - 120 * 24 * 3_600_000).toISOString().slice(0, 10);
    return {
      from: searchParams.get("from") ?? defaultFrom,
      to: searchParams.get("to") ?? now.toISOString().slice(0, 10),
      region: searchParams.get("region"),
    };
  }, [searchParams]);
}

export function AnalyticsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { from, to, region } = useRangeParams();
  const overview = useOverview();
  const analytics = useAnalytics({ from, to, region });
  const scarId = searchParams.get("scar");
  const scar = useBurnScar(scarId);

  const setParam = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value);
    else params.delete(key);
    router.replace(params.toString() ? `/analytics?${params}` : "/analytics", { scroll: false });
  };

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.headRow}>
          <h1 className={styles.title}>Аналитика</h1>
          <div className={styles.controls}>
            <select className={styles.select} value={region ?? ""} onChange={(event) => setParam("region", event.target.value || null)} aria-label="Регион">
              <option value="">Все регионы</option>
              {overview.data?.regions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            <input
              className={styles.select}
              type="date"
              aria-label="С"
              value={from}
              max={to}
              onChange={(event) => setParam("from", event.target.value)}
            />
            <input
              className={styles.select}
              type="date"
              aria-label="По"
              value={to}
              min={from}
              onChange={(event) => setParam("to", event.target.value)}
            />
          </div>
        </div>

        {analytics.isError && <ErrorMessage error={analytics.error} onRetry={() => analytics.refetch()} retrying={analytics.isFetching} />}

        {analytics.isPending && (
          <div className={styles.metrics}>
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className={styles.metric}>
                <Skeleton width="60%" height={10} />
                <Skeleton width="40%" height={24} style={{ marginTop: 8 }} />
              </div>
            ))}
          </div>
        )}

        {analytics.data && (
          <>
            <div className={styles.metrics}>
              <div className={styles.metric}>
                <div className={styles.metricLabel}>События</div>
                <span className={styles.metricValue}>{formatInteger(analytics.data.totals.incidents)}</span>
              </div>
              <div className={styles.metric}>
                <div className={styles.metricLabel}>Суммарная площадь гарей</div>
                <span className={styles.metricValue}>{formatArea(analytics.data.totals.burned_area_ha)}</span>
              </div>
              <div className={styles.metric}>
                <div className={styles.metricLabel}>Высокая severity</div>
                <span className={styles.metricValue}>{formatArea(analytics.data.totals.high_severity_ha)}</span>
                <div className={styles.metricSub}>{formatPercent(analytics.data.totals.high_severity_share)} от площади</div>
              </div>
              <div className={styles.metric}>
                <div className={styles.metricLabel}>Среднее время подтверждения</div>
                <span className={styles.metricValue}>{formatDuration(analytics.data.totals.mean_confirmation_minutes)}</span>
              </div>
            </div>

            <div className={styles.grid}>
              <div className={styles.panel}>
                <div className={styles.panelHeader}>Площадь гарей и число событий по неделям</div>
                <div className={styles.chartBody}>
                  <TrendChart series={analytics.data.series} />
                </div>
              </div>
              <div className={styles.panel}>
                <div className={styles.panelHeader}>По регионам</div>
                <ul className={styles.regionList}>
                  {analytics.data.regions.map((item) => {
                    const share = item.burned_area_ha / Math.max(1, analytics.data!.totals.burned_area_ha);
                    return (
                      <li key={item.region_id} className={styles.regionRow}>
                        <span className={styles.regionName}>{item.name}</span>
                        <span className={styles.regionValue}>{formatArea(item.burned_area_ha)}</span>
                        <div className={styles.regionBar}>
                          <span style={{ width: `${Math.round(share * 100)}%` }} />
                        </div>
                      </li>
                    );
                  })}
                  {analytics.data.regions.length === 0 && (
                    <li style={{ padding: 16, color: "var(--text-tertiary)", fontSize: 12.5 }}>Нет данных</li>
                  )}
                </ul>
              </div>
            </div>

            <div className={styles.panel}>
              <div className={styles.panelHeader}>Крупнейшие гари</div>
              {analytics.data.largest_burn_scars.length === 0 ? (
                <StateMessage title="Нет гарей за период" />
              ) : (
                <table className={styles.scarTable}>
                  <thead>
                    <tr>
                      <th>Название</th>
                      <th>Регион</th>
                      <th>Начало пожара</th>
                      <th style={{ textAlign: "right" }}>Площадь</th>
                      <th>Тяжесть</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.data.largest_burn_scars.map((item) => {
                      const total = Math.max(1, item.severity.low_ha + item.severity.moderate_ha + item.severity.high_ha);
                      return (
                        <tr key={item.id} onClick={() => setParam("scar", item.id)}>
                          <td>{item.name}</td>
                          <td>{item.district}</td>
                          <td>{formatDateLong(item.fire_started_on)}</td>
                          <td className={styles.numeric}>{formatArea(item.area_ha)}</td>
                          <td>
                            <div className={styles.severityBar} title={`Низкая ${formatArea(item.severity.low_ha)} · Средняя ${formatArea(item.severity.moderate_ha)} · Высокая ${formatArea(item.severity.high_ha)}`}>
                              <span style={{ width: `${(item.severity.low_ha / total) * 100}%`, background: SEVERITY_COLOR.low }} />
                              <span style={{ width: `${(item.severity.moderate_ha / total) * 100}%`, background: SEVERITY_COLOR.moderate }} />
                              <span style={{ width: `${(item.severity.high_ha / total) * 100}%`, background: SEVERITY_COLOR.high }} />
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </div>

      {scarId && (
        <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Сравнение до и после">
          <div className={styles.dialog}>
            <div className={styles.dialogHeader}>
              <div>
                <h2 className={styles.dialogTitle}>{scar.data?.name ?? scarId}</h2>
                {scar.data && <div className={styles.dialogSub}>{scar.data.district}, {scar.data.region}</div>}
              </div>
              <span style={{ flex: 1 }} />
              <IconButton label="Закрыть" icon={<X size={16} />} onClick={() => setParam("scar", null)} />
            </div>
            <div className={styles.dialogBody}>
              {scar.isPending && <Skeleton height={320} />}
              {scar.isError && <ErrorMessage error={scar.error} onRetry={() => scar.refetch()} />}
              {scar.data && <BurnScarCompare scar={scar.data} />}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
