"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { StateMessage } from "@/components/ui/StateMessage";
import { api } from "@/lib/api/endpoints";
import { useMlStatus, useTrainChips } from "@/lib/api/queries";
import type { TrainChipKind, UploadPredictResult } from "@/lib/api/types";
import { PredictionResult } from "./PredictionResult";
import styles from "./predict.module.css";

export function PredictView() {
  const [task, setTask] = useState<TrainChipKind>("bs");
  const [source, setSource] = useState<"train" | "upload">("upload");
  const [selected, setSelected] = useState("");
  const [runningChip, setRunningChip] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadPredictResult | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const chips = useTrainChips({ kind: task, limit: 1000 });
  const ml = useMlStatus();
  const chipId = selected || chips.data?.items[0]?.chip_id || "";

  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (source === "train") {
      setRunningChip(chipId);
      return;
    }
    if (!file) return;
    setUploadError("");
    setUploadResult(null);
    setUploading(true);
    try {
      setUploadResult(await api.ml.upload(task, file));
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Не удалось обработать ZIP");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Предикт"
          description="AF + BS GOLD v006 · загрузка своего чипа или выбор сцены TRAIN."
          actions={<Link className={styles.ghostLink} href="/explorer">Official TRAIN</Link>}
        />
        <div className={styles.workspace}>
          <Card className={styles.panel}>
            <form className={styles.form} onSubmit={run}>
              <SegmentedControl
                label="Источник данных"
                value={source}
                onChange={(value) => {
                  setSource(value);
                  setRunningChip("");
                  setUploadResult(null);
                  setUploadError("");
                }}
                options={[
                  { value: "upload", label: "Свой файл" },
                  { value: "train", label: "Official TRAIN" },
                ]}
              />
              <SegmentedControl
                label="Задача"
                value={task}
                onChange={(value) => {
                  setTask(value);
                  setSelected("");
                  setRunningChip("");
                  setUploadResult(null);
                  setUploadError("");
                  setFile(null);
                }}
                options={[{ value: "af", label: "AF" }, { value: "bs", label: "BS" }]}
              />
              {source === "train" ? (
                <>
                  <div className={styles.formHeading}>
                    <div>
                      <h2>OFFICIAL TRAIN</h2>
                      <p>Выберите подготовленную спутниковую сцену.</p>
                    </div>
                  </div>
                  {chips.isPending && <StateMessage title="Загрузка сцен…" />}
                  {chips.isError && <StateMessage title="Не удалось загрузить сцены" tone="error" />}
                  {chips.data && (
                    <label>
                      Сцена
                      <select
                        aria-label="Сцена"
                        value={chipId}
                        onChange={(event) => setSelected(event.target.value)}
                        className={styles.sceneSelect}
                      >
                        {chips.data.items.map((chip) => (
                          <option key={chip.chip_id} value={chip.chip_id}>
                            {chip.chip_id} · {chip.fire_event_id || chip.satellite || task.toUpperCase()}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  {!chips.data?.available && chips.data && (
                    <StateMessage title="TRAIN не подключён на сервере" detail="Можно загрузить свой ZIP с каналами чипа." />
                  )}
                  <p>Вход AF: VIIRS + AUX. Вход BS: Sentinel-2 PRE/POST, Sentinel-1 PRE/POST и AUX.</p>
                  {chipId && <Link className={styles.ghostLink} href={`/explorer?chip=${encodeURIComponent(chipId)}`}>Открыть PRE / POST и исходные слои</Link>}
                </>
              ) : (
                <>
                  <div className={styles.formHeading}>
                    <div>
                      <h2>СВОЙ ЧИП</h2>
                      <p>Загрузите один ZIP с TIFF-файлами одного чипа, до 64 МБ.</p>
                    </div>
                  </div>
                  <label className={styles.dropzone} data-has-file={Boolean(file)}>
                    <strong>{file?.name || "Выбрать ZIP с чипом"}</strong>
                    <span>TIFF 256×256, имена файлов с общим ID чипа</span>
                    <input
                      type="file"
                      accept=".zip,application/zip"
                      onChange={(event) => {
                        setFile(event.target.files?.[0] || null);
                        setUploadResult(null);
                        setUploadError("");
                      }}
                    />
                  </label>
                  <p>
                    {task === "af"
                      ? "В ZIP нужны ID_VIIRS_I1-I5.tif (8 каналов) и ID_AUX.tif (5 каналов)."
                      : "В ZIP нужны ID_Sentinel-2_pre.tif, ID_Sentinel-2_post.tif (по 10 каналов), ID_Sentinel-1_pre.tif, ID_Sentinel-1_post.tif (по 2 канала) и ID_AUX.tif (3 канала)."}
                    {" "}Одиночный JPEG для этой модели не подходит.
                  </p>
                  {uploadError && <StateMessage title="Ошибка загрузки" detail={uploadError} tone="error" />}
                </>
              )}
              <div className={styles.statusRow}>
                <span data-ready={ml.data?.[task].ready}>
                  {ml.data?.[task].ready ? "Модель готова" : "Модель недоступна"}
                </span>
                <em>{ml.data?.[task].model_version}</em>
              </div>
              <button
                className={styles.runButton}
                type="submit"
                disabled={!ml.data?.[task].ready || uploading || (source === "train" ? !chipId || !chips.data?.available : !file)}
              >
                {uploading ? "Выполняется предикт…" : "Запустить предикт"}
              </button>
            </form>
          </Card>
          <div className={styles.resultColumn}>
            {source === "upload" && uploadResult ? (
              <Card className={styles.resultCard}>
                <div className={styles.resultHead}>
                  <h2>MODEL OUTPUT · {uploadResult.input.chip_id}</h2>
                  <span>{uploadResult.model_version} · {uploadResult.runtime_ms.toLocaleString("ru-RU")} мс</span>
                </div>
                <p>{uploadResult.detail}</p>
                <div className={styles.viewer}>
                  <figure>
                    <img src={`data:image/png;base64,${uploadResult.input.preview_png_b64}`} alt="Загруженный чип" />
                    <figcaption>Входные каналы</figcaption>
                  </figure>
                  <figure>
                    <img src={`data:image/png;base64,${uploadResult.mask_png_b64}`} alt="Предсказанная маска" />
                    <figcaption>Предсказанная маска</figcaption>
                  </figure>
                </div>
                <dl className={styles.metrics}>
                  {(task === "af"
                    ? [["Fire pixels", uploadResult.n_fire_px], ["Mean confidence", uploadResult.confidence_mean]]
                    : [["Burn area, га", uploadResult.total_area_ha], ["Low, га", uploadResult.area_low_ha], ["Moderate, га", uploadResult.area_moderate_ha], ["High, га", uploadResult.area_high_ha]]
                  ).map(([label, value]) => (
                    <div key={String(label)}><dt>{label}</dt><dd>{value == null ? "—" : Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 3 })}</dd></div>
                  ))}
                </dl>
                {task === "bs" && <div className={styles.legendSeverity}><span data-sev="1">Low</span><span data-sev="2">Moderate</span><span data-sev="3">High</span></div>}
              </Card>
            ) : source === "train" && runningChip ? (
              <PredictionResult key={runningChip} chipId={runningChip} />
            ) : (
              <Card className={styles.hintCard}>
                <p>{source === "upload" ? "После загрузки появятся маска и оценка площади или число термоточек. Для оценки качества нужна разметка." : "После запуска: GT / Prediction / Errors, local metrics, площадь по severity и векторный экспорт. Метрики TRAIN являются in-sample."}</p>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
