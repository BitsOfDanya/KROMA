"use client";

import Link from "next/link";
import { useTrainChips } from "@/lib/api/queries";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { IncidentInspector } from "@/features/incidents/IncidentInspector";

import { EventsTable } from "./EventsTable";
import styles from "./events.module.css";

export function EventsView() {
  const train = useTrainChips({ kind: "bs", limit: 12 });
  const searchParams = useSearchParams();
  const router = useRouter();
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    searchParams.get("incident"),
  );

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (selectedId) params.set("incident", selectedId);
    else params.delete("incident");
    const next = params.toString();
    if (next !== searchParams.toString())
      router.replace(next ? `/events?${next}` : "/events", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  return (
    <div className={styles.page}>
      <div className={styles.tableColumn} data-split={Boolean(selectedId)}>
        <p style={{ padding: "12px 20px", color: "var(--text-secondary)" }}>
          SCENARIO · демонстрационные инциденты. Official TRAIN и MODEL OUTPUT
          доступны в разделе «Данные».
        </p>
        <details
          style={{
            margin: "0 20px 12px",
            padding: 12,
            background: "var(--surface)",
            borderRadius: 8,
          }}
        >
          <summary>
            OFFICIAL TRAIN · события BS ({train.data?.counts.bs ?? "…"} сцен)
          </summary>
          <p>
            PRE → POST → GT severity → MODEL OUTPUT. Связь с AF не назначается
            без подтверждающих метаданных.
          </p>
          {train.isError && (
            <p>
              Каталог TRAIN недоступен; откройте «Данные» для повторной
              загрузки.
            </p>
          )}
          <ul>
            {train.data?.items.map((chip) => (
              <li key={chip.chip_id}>
                <Link href={`/explorer?chip=${chip.chip_id}`}>
                  {chip.fire_event_id} · {chip.chip_id}
                </Link>{" "}
                · {chip.date_pre} → {chip.date_post} · GT {chip.burn_area_ha} га
              </li>
            ))}
          </ul>
          <Link href="/explorer">Все сцены и поиск событий</Link>
        </details>
        <EventsTable selectedId={selectedId} onSelect={setSelectedId} />
      </div>
      {selectedId && (
        <div className={styles.detailColumn}>
          <IncidentInspector
            incidentId={selectedId}
            onClose={() => setSelectedId(null)}
          />
        </div>
      )}
    </div>
  );
}
