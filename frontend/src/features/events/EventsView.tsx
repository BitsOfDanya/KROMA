"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { IncidentInspector } from "@/features/incidents/IncidentInspector";

import { EventsTable } from "./EventsTable";
import styles from "./events.module.css";

export function EventsView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get("incident"));

  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (selectedId) params.set("incident", selectedId);
    else params.delete("incident");
    const next = params.toString();
    if (next !== searchParams.toString()) router.replace(next ? `/events?${next}` : "/events", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  return (
    <div className={styles.page}>
      <div className={styles.tableColumn} data-split={Boolean(selectedId)}>
        <EventsTable selectedId={selectedId} onSelect={setSelectedId} />
      </div>
      {selectedId && (
        <div className={styles.detailColumn}>
          <IncidentInspector incidentId={selectedId} onClose={() => setSelectedId(null)} />
        </div>
      )}
    </div>
  );
}
