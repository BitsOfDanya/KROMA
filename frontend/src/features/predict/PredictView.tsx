"use client";

import { useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { useMlStatus, useTrainChips } from "@/lib/api/queries";
import type { TrainChipKind } from "@/lib/api/types";
import { PredictionResult } from "./PredictionResult";
import styles from "./predict.module.css";

export function PredictView() {
  const [task, setTask] = useState<TrainChipKind>("bs");
  const [selected, setSelected] = useState("");
  const [runningChip, setRunningChip] = useState("");
  const chips = useTrainChips({ kind: task, limit: 1000 });
  const ml = useMlStatus();
  const chipId = selected || chips.data?.items[0]?.chip_id || "";
  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Предикт"
          description="AF + BS GOLD v006 · полный пакет Official TRAIN · маски, валидация, площади и экспорт."
          actions={
            <Link className={styles.ghostLink} href="/explorer">
              Official TRAIN
            </Link>
          }
        />
        <div className={styles.workspace}>
          <Card className={styles.panel}>
            <form
              className={styles.form}
              onSubmit={(event) => {
                event.preventDefault();
                setRunningChip(chipId);
              }}
            >
              <div className={styles.formHeading}>
                <div>
                  <h2>OFFICIAL TRAIN</h2>
                  <p>Выберите подготовленную спутниковую сцену.</p>
                </div>
              </div>
              <SegmentedControl
                label="Задача"
                value={task}
                onChange={(value) => {
                  setTask(value);
                  setSelected("");
                  setRunningChip("");
                }}
                options={[
                  { value: "af", label: "AF" },
                  { value: "bs", label: "BS" },
                ]}
              />
              {chips.isPending && <StateMessage title="Загрузка сцен…" />}
              {chips.isError && (
                <ErrorMessage
                  error={chips.error}
                  onRetry={() => chips.refetch()}
                />
              )}
              {chips.data && (
                <label>
                  Сцена
                  <select
                    aria-label="Сцена"
                    value={chipId}
                    onChange={(event) => setSelected(event.target.value)}
                    style={{
                      width: "100%",
                      padding: 12,
                      marginTop: 8,
                      background: "var(--surface)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {chips.data.items.map((chip) => (
                      <option key={chip.chip_id} value={chip.chip_id}>
                        {chip.chip_id} ·{" "}
                        {chip.fire_event_id ||
                          chip.satellite ||
                          task.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {chips.data?.items.length === 0 && (
                <StateMessage
                  title="TRAIN не подключён"
                  detail="Укажите KROMA_TRAIN_ROOT и соберите индекс."
                />
              )}
              <div className={styles.statusRow}>
                <span data-ready={ml.data?.[task].ready}>
                  {ml.data?.[task].ready
                    ? "Модель готова"
                    : "Модель недоступна"}
                </span>
                <em>{ml.data?.[task].model_version}</em>
              </div>
              <p>
                Вход AF: VIIRS + AUX. Вход BS: Sentinel-2 PRE/POST, AUX и
                Sentinel-1. Обычный JPEG не содержит необходимых каналов.
              </p>
              <button
                className={styles.runButton}
                type="submit"
                disabled={
                  !chipId || !chips.data?.available || !ml.data?.[task].ready
                }
              >
                Запустить предикт
              </button>
              {chipId && (
                <Link
                  className={styles.ghostLink}
                  href={`/explorer?chip=${chipId}`}
                >
                  Открыть PRE / POST и исходные слои
                </Link>
              )}
            </form>
          </Card>
          <div className={styles.resultColumn}>
            {runningChip ? (
              <PredictionResult key={runningChip} chipId={runningChip} />
            ) : (
              <Card className={styles.hintCard}>
                <p>
                  После запуска: GT / Prediction / Errors, local metrics,
                  площадь по severity и векторный экспорт. Метрики TRAIN
                  являются in-sample.
                </p>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
