"use client";

import { ArrowUpRight, History, X } from "lucide-react";
import Link from "next/link";

import { IconButton } from "@/components/ui/IconButton";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorMessage } from "@/components/ui/StateMessage";
import { StatusPill } from "@/components/ui/StatusPill";
import { useIncident } from "@/lib/api/queries";
import { formatCoordinate, formatDateTime, formatExact } from "@/lib/format";
import { STATUS_TITLE } from "@/lib/labels";
import { incidentStateAt } from "@/lib/replay";
import { useWorkspace } from "@/state/workspace";

import { IncidentDetails } from "./IncidentDetails";
import styles from "./incidents.module.css";

export function IncidentInspector({ incidentId }: { incidentId: string }) {
  const query = useIncident(incidentId);
  const cursor = useWorkspace((state) => state.cursor);
  const selectIncident = useWorkspace((state) => state.selectIncident);
  const detail = query.data;
  const state = detail ? incidentStateAt(detail, cursor) : null;

  return (
    <aside className={styles.inspector} aria-label={`Событие ${incidentId}`}>
      <header className={styles.inspectorHeader}>
        <div className={styles.inspectorTop}>
          <span className={styles.inspectorId}>{incidentId}</span>
          {state && <StatusPill status={state.status} />}
          <span style={{ flex: 1 }} />
          <IconButton label="Закрыть инспектор" size="sm" showTooltip={false} icon={<X size={15} />} onClick={() => selectIncident(null)} />
        </div>
        {detail && state ? (
          <>
            <h2 className={styles.inspectorTitle}>{STATUS_TITLE[state.status]}</h2>
            <div className={styles.inspectorLocation}>
              {detail.district}, {detail.region}
            </div>
            <div className={styles.inspectorSub}>
              <span className="mono">{formatCoordinate(detail.centroid)}</span> · обнаружен{" "}
              <span title={formatExact(detail.first_detected_at)}>{formatDateTime(detail.first_detected_at)}</span>
            </div>
          </>
        ) : (
          <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
            <Skeleton width="60%" height={18} />
            <Skeleton width="45%" />
          </div>
        )}
      </header>
      {cursor !== null && state && (
        <div className={styles.replayNote}>
          <History size={13} />
          {state.visible ? `Состояние на ${formatDateTime(cursor)}` : `На ${formatDateTime(cursor)} событие ещё не обнаружено`}
        </div>
      )}
      <div className={styles.inspectorBody}>
        {query.isError && <ErrorMessage error={query.error} onRetry={() => query.refetch()} retrying={query.isFetching} />}
        {query.isPending && (
          <div style={{ display: "grid", gap: 10, padding: 16 }}>
            <Skeleton height={60} />
            <Skeleton height={14} width="80%" />
            <Skeleton height={14} width="70%" />
            <Skeleton height={14} width="75%" />
          </div>
        )}
        {detail && state && <IncidentDetails detail={detail} state={state} />}
      </div>
      {detail && (
        <footer className={styles.inspectorFooter}>
          <Link className={styles.footerButton} href={`/events?incident=${encodeURIComponent(detail.id)}`}>
            Открыть подробный анализ <ArrowUpRight size={14} />
          </Link>
          {detail.burn_scar_id && (
            <Link className={styles.footerButton} href={`/analytics?scar=${encodeURIComponent(detail.burn_scar_id)}`}>
              Гарь до / после
            </Link>
          )}
        </footer>
      )}
    </aside>
  );
}
