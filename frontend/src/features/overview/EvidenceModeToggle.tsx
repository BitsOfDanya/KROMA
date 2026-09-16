"use client";

import { History } from "lucide-react";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useOverview } from "@/lib/api/queries";
import { formatDateTime, formatInteger } from "@/lib/format";
import { useWorkspace, type EvidenceMode } from "@/state/workspace";

import styles from "./overview.module.css";

export function EvidenceModeToggle() {
  const mode = useWorkspace((state) => state.evidenceMode);
  const setMode = useWorkspace((state) => state.setEvidenceMode);
  const cursor = useWorkspace((state) => state.cursor);
  const overview = useOverview();

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
                {overview.data && (
                  <span style={{ color: "var(--text-tertiary)", fontSize: 11 }} className="tabular">
                    {formatInteger(overview.data.raw_detections_7d)}
                  </span>
                )}
              </>
            ),
            title: "Сырые спутниковые детекции за 7 суток",
          },
        ]}
      />
      {cursor !== null && (
        <span className={styles.replayBadge} role="status">
          <History size={13} strokeWidth={2} />
          Ретроспектива · {formatDateTime(cursor)}
        </span>
      )}
    </div>
  );
}
