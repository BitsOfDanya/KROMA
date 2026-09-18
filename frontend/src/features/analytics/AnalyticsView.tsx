"use client";

import { Activity, Clock3, Flame, Trees, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { Card, CardHeader } from "@/components/ui/Card";
import { SelectField, TextField } from "@/components/ui/Field";
import { IconButton } from "@/components/ui/IconButton";
import { PageHeader } from "@/components/ui/PageHeader";
import { MetricCard } from "@/components/ui/MetricCard";
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
        <PageHeader
          title="Пожары в цифрах"
          description="Как меняется ситуация: события, последствия и время реагирования."
          actions={
            <div className={styles.controls}>
            <Link className={styles.analysisLink} href="/analytics?tab=area">Анализ территории</Link>
            <SelectField className={styles.regionSelect} value={region ?? ""} onChange={(event) => setParam("region", event.target.value || null)} aria-label="Регион">
              <option value="">Все регионы</option>
              {overview.data?.regions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </SelectField>
            <TextField
              className={styles.dateField}
              type="date"
              aria-label="С"
              value={from}
              max={to}
              onChange={(event) => setParam("from", event.target.value)}
            />
            <TextField
              className={styles.dateField}
              type="date"
              aria-label="По"
              value={to}
              min={from}
              onChange={(event) => setParam("to", event.target.value)}
            />
            </div>
          }
        />

        {analytics.isError && <ErrorMessage error={analytics.error} onRetry={() => analytics.refetch()} retrying={analytics.isFetching} />}

        {analytics.isPending && (
          <div className={styles.metrics}>
            {Array.from({ length: 4 }, (_, index) => (
              <Card key={index} className={styles.metric} padding="md">
                <Skeleton width="60%" height={10} />
                <Skeleton width="40%" height={24} style={{ marginTop: 8 }} />
              </Card>
            ))}
          </div>
        )}

        {analytics.data && (
          <>
            <div className={styles.metrics}>
              <MetricCard label="Всего событий" value={formatInteger(analytics.data.totals.incidents)} description="За выбранный период" icon={<Activity size={20} />} />
              <MetricCard label="Площадь гарей" value={formatArea(analytics.data.totals.burned_area_ha)} description="Территория, пройденная огнём" icon={<Trees size={20} />} tone="positive" />
              <MetricCard label="Сильные повреждения" value={formatArea(analytics.data.totals.high_severity_ha)} description={`${formatPercent(analytics.data.totals.high_severity_share)} от общей площади гарей`} icon={<Flame size={20} />} tone="danger" />
              <MetricCard label="Время подтверждения" value={formatDuration(analytics.data.totals.mean_confirmation_minutes)} description="В среднем после обнаружения" icon={<Clock3 size={20} />} tone="info" />
            </div>

            <div className={styles.grid}>
              <Card className={styles.panel}>
                <CardHeader title="Как менялась ситуация" action={<span className={styles.chartHint}>По неделям</span>} />
                <div className={styles.chartBody}>
                  <div className={styles.chartLegend}>
                    <span><i style={{ background: "var(--burn-scar)" }} />Площадь гарей</span>
                    <span><i style={{ background: "var(--observation)" }} />Число событий</span>
                  </div>
                  <TrendChart series={analytics.data.series} />
                </div>
              </Card>
              <Card className={styles.panel}>
                <CardHeader title="По регионам" />
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
              </Card>
            </div>

            <Card className={styles.panel}>
              <CardHeader title="Крупнейшие гари" />
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
            </Card>
          </>
        )}
      </div>

      {scarId && (
        <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Подложка и демонстрационный результат классификации">
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
