"use client";

import { ImageUp, RotateCw, ShieldAlert, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useRef, useState, type DragEvent, type FormEvent } from "react";

import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { ErrorMessage } from "@/components/ui/StateMessage";
import { api } from "@/lib/api/endpoints";
import { useMlStatus } from "@/lib/api/queries";
import type { TrainChipKind, UploadPredictResult } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";

import styles from "./predict.module.css";

function b64src(b64: string | null | undefined) {
  return b64 ? `data:image/png;base64,${b64}` : null;
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function PredictView() {
  const ml = useMlStatus();
  const inputRef = useRef<HTMLInputElement>(null);
  const [task, setTask] = useState<TrainChipKind>("af");
  const [file, setFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<UploadPredictResult | null>(null);

  const ready = task === "af" ? Boolean(ml.data?.af.ready) : Boolean(ml.data?.bs.ready);

  const pickFile = useCallback((next: File | null) => {
    setFile(next);
    setResult(null);
    setError(null);
    setLocalPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      if (next && (next.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(next.name))) {
        return URL.createObjectURL(next);
      }
      return null;
    });
  }, []);

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const next = event.dataTransfer.files?.[0] ?? null;
    if (next) pickFile(next);
  };

  const run = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) return;
    setRunning(true);
    setError(null);
    try {
      const payload = await api.ml.upload(task, file);
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err : new ApiError("Ошибка предикта", 0, "/api/v1/inference/upload"));
    } finally {
      setRunning(false);
    }
  };

  const inputSrc = b64src(result?.input.preview_png_b64) ?? localPreview;
  const maskSrc = b64src(result?.mask_png_b64);

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Предикт"
          description="Загрузите снимок или GeoTIFF — модель AF/BS вернёт маску и метрики. Без весов в ml/artifacts инференс недоступен, превью входа всё равно строится."
          actions={
            <Link className={styles.ghostLink} href="/explorer">
              Official TRAIN
            </Link>
          }
        />

        <div className={styles.workspace}>
          <Card className={styles.panel}>
            <form onSubmit={run} className={styles.form}>
              <div className={styles.formHeading}>
                <ImageUp size={17} />
                <div>
                  <h2>Входной файл</h2>
                  <p>PNG / JPEG / GeoTIFF · до 64 МБ</p>
                </div>
              </div>

              <SegmentedControl
                label="Задача"
                value={task}
                onChange={(value) => {
                  setTask(value);
                  setResult(null);
                }}
                options={[
                  { value: "af", label: "AF", title: "Active Fire · LightGBM" },
                  { value: "bs", label: "BS", title: "Burn Severity · GOLD/v004" },
                ]}
              />

              <div
                className={styles.dropzone}
                data-dragging={dragging}
                data-has-file={Boolean(file)}
                onDragEnter={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    inputRef.current?.click();
                  }
                }}
              >
                <Upload size={22} />
                {file ? (
                  <div>
                    <strong className="mono">{file.name}</strong>
                    <span>{formatBytes(file.size)} · {file.type || "binary"}</span>
                  </div>
                ) : (
                  <div>
                    <strong>Перетащите файл сюда</strong>
                    <span>или нажмите, чтобы выбрать</span>
                  </div>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept=".tif,.tiff,.png,.jpg,.jpeg,.webp,image/*,image/tiff"
                  hidden
                  onChange={(event) => pickFile(event.target.files?.[0] ?? null)}
                />
              </div>

              <div className={styles.statusRow}>
                <span data-ready={ready}>{ready ? "Модель готова" : "Веса не смонтированы"}</span>
                <em>{task === "af" ? ml.data?.af.expected : ml.data?.bs.expected}</em>
              </div>

              <button className={styles.runButton} type="submit" disabled={!file || running}>
                {running ? <RotateCw size={16} className={styles.spin} /> : <ImageUp size={16} />}
                {running ? "Считаем…" : "Запустить предикт"}
              </button>
            </form>
          </Card>

          <div className={styles.resultColumn}>
            {error && (
              <ErrorMessage
                error={error}
                onRetry={() => {
                  if (file) {
                    void (async () => {
                      setRunning(true);
                      setError(null);
                      try {
                        setResult(await api.ml.upload(task, file));
                      } catch (err) {
                        setError(err instanceof Error ? err : new Error("Ошибка"));
                      } finally {
                        setRunning(false);
                      }
                    })();
                  }
                }}
                retrying={running}
              />
            )}

            {!result && !error && (
              <Card className={styles.hintCard}>
                <p>
                  AF: лучше VIIRS / thermal GeoTIFF. BS: Sentinel-2 pre/post стек или RGB-сцена. После загрузки
                  появится превью входа и маска модели.
                </p>
              </Card>
            )}

            {(inputSrc || result) && (
              <Card className={styles.resultCard}>
                <div className={styles.resultHead}>
                  <h2>Результат</h2>
                  {result && (
                    <span data-status={result.status}>
                      {result.status === "ok" ? "ok" : "unavailable"} · {Math.round(result.runtime_ms)} мс ·{" "}
                      {result.model_version}
                    </span>
                  )}
                </div>

                {result?.status === "unavailable" && (
                  <div className={styles.notice}>
                    <ShieldAlert size={16} />
                    <p>
                      {result.detail ??
                        "Модель не загружена. Превью входа построено; положите веса в ml/artifacts и повторите."}
                    </p>
                  </div>
                )}

                <div className={styles.viewer}>
                  <figure>
                    {inputSrc ? <img src={inputSrc} alt="Вход" /> : <div className={styles.empty}>Нет превью</div>}
                    <figcaption>Вход</figcaption>
                  </figure>
                  <figure>
                    {maskSrc ? (
                      <img src={maskSrc} alt="Предикт" />
                    ) : (
                      <div className={styles.empty}>
                        {result ? "Маска недоступна" : "Ожидание предикта"}
                      </div>
                    )}
                    <figcaption>Предикт</figcaption>
                  </figure>
                </div>

                {result && (
                  <dl className={styles.metrics}>
                    <div>
                      <dt>Shape</dt>
                      <dd className="mono">{result.input.shape.join("×")}</dd>
                    </div>
                    <div>
                      <dt>Bands</dt>
                      <dd>{result.input.bands}</dd>
                    </div>
                    {result.task === "af" ? (
                      <>
                        <div>
                          <dt>Fire px</dt>
                          <dd>{result.n_fire_px ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Confidence</dt>
                          <dd>
                            {result.confidence_mean != null ? result.confidence_mean.toFixed(3) : "—"}
                          </dd>
                        </div>
                      </>
                    ) : (
                      <>
                        <div>
                          <dt>Burn area</dt>
                          <dd>{result.total_area_ha != null ? `${result.total_area_ha} га` : "—"}</dd>
                        </div>
                        <div>
                          <dt>L / M / H</dt>
                          <dd>
                            {[result.area_low_ha, result.area_moderate_ha, result.area_high_ha]
                              .map((v) => (v != null ? v : "—"))
                              .join(" / ")}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>
                )}

                {task === "bs" && (
                  <div className={styles.legendSeverity}>
                    <span data-sev="1">Low</span>
                    <span data-sev="2">Moderate</span>
                    <span data-sev="3">High</span>
                  </div>
                )}
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
