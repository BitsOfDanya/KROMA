"use client";

import { History } from "lucide-react";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useLiveStatus, useOverview } from "@/lib/api/queries";
import { formatDateTime, formatInteger } from "@/lib/format";
import { useWorkspace, type EvidenceMode } from "@/state/workspace";

import styles from "./overview.module.css";

export function EvidenceModeToggle() {
  const mode = useWorkspace((state) => state.evidenceMode);
  const setMode = useWorkspace((state) => state.setEvidenceMode);
  const cursor = useWorkspace((state) => state.cursor);
  const appMode = useWorkspace((state) => state.appMode);
  const overview = useOverview();
  const live = useLiveStatus();
  const detectionCount = appMode === "live" ? live.data?.detection_count : overview.data?.raw_detections_7d;

  return (
    <div className={styles.modeToggle}>
      <SegmentedControl<EvidenceMode>
        label="Режим отображения"
        value={mode}
        onChange={setMode}
        options={[
          { value: "events", label: "События", title: "Обработанные события KROMA" },
          {
            value: "data",
            label: (
              <>
                Данные
                {detectionCount !== undefined && (
                  <span style={{ color: "var(--text-tertiary)", fontSize: 11 }} className="tabular">
                    {formatInteger(detectionCount)}
                  </span>
                )}
              </>
            ),
            title:
              appMode === "live"
                ? "Сырые детекции NASA FIRMS в кэше"
                : "Сырые спутниковые детекции за 7 суток",
          },
        ]}
      />
      {cursor !== null && (
        <span className={styles.replayBadge} role="status">
          <History size={13} strokeWidth={2} />
          {appMode === "live" ? "История" : "Ретроспектива"} · {formatDateTime(cursor)}
        </span>
      )}
    </div>
  );
}
