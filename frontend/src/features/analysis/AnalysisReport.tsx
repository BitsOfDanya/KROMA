"use client";

import { Download, FileJson, Info, TriangleAlert } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api/endpoints";
import type { AnalysisQuery, AnalysisResult } from "@/lib/api/types";
import { formatArea, formatPercent } from "@/lib/format";

import styles from "./analysis.module.css";

const ORIGIN_LABEL = {
  model_output: "Подготовленный результат модели",
  reference: "Эталонные данные",
  synthetic_demo: "Синтетический проверочный набор",
} as const;

const STATUS_LABEL = {
  ok: "Результат рассчитан",
  empty: "Обследовано, обнаружений нет",
  no_coverage: "Нет покрытия выбранной области",
  no_valid_data: "Нет валидных пикселей",
} as const;

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function AnalysisReport({ result, query }: { result: AnalysisResult; query: AnalysisQuery }) {
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const download = async (kind: "contours" | "csv" | "json") => {
    setDownloading(kind);
    setDownloadError(null);
    try {
      const file = kind === "contours"
        ? await api.analysis.contours(query, result.result_id)
        : await api.analysis.report(query, result.result_id, kind);
      save(file.blob, file.filename);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Не удалось подготовить файл");
    } finally {
      setDownloading(null);
    }
  };

  const total = result.summary.total_burned_area_ha;
  return (
    <section className={styles.reportCard} aria-labelledby="analysis-report-title">
      <div className={styles.reportHeader}>
        <div>
          <span className={styles.eyebrow}>{STATUS_LABEL[result.summary.status]}</span>
          <h2 id="analysis-report-title">Справка по территории и периоду</h2>
          <p>{result.request.from} — {result.request.to}, включительно · UTC</p>
        </div>
        <span className={styles.originBadge} data-origin={result.provenance.origin}>
          {ORIGIN_LABEL[result.provenance.origin]}
        </span>
      </div>

      {result.warnings.length > 0 && (
        <div className={styles.warningList}>
          {result.warnings.map((warning) => (
            <p key={warning.code}><TriangleAlert size={15} />{warning.message}</p>
          ))}
        </div>
      )}

      <div className={styles.reportMetrics}>
        <div><span>Выгоревшая площадь</span><strong>{total === null ? "Нет данных" : formatArea(total)}</strong></div>
        <div><span>Уникальные гари</span><strong>{result.summary.burn_scar_count}</strong></div>
        <div><span>Термоточки</span><strong>{result.summary.hotspot_count}</strong></div>
        <div><span>Валидно обследовано</span><strong>{result.coverage.valid_area_ha === null ? "Неизвестно" : formatArea(result.coverage.valid_area_ha)}</strong></div>
      </div>

      <div className={styles.severityDistribution} aria-hidden="true">
        {result.summary.severity.map((item) => (
          <span
            key={item.class_id}
            data-severity={item.severity}
            style={{ width: `${item.share === null ? 0 : item.share * 100}%` }}
          />
        ))}
      </div>
      <table className={styles.severityTable}>
        <caption className="visually-hidden">Площадь по степеням поражения</caption>
        <thead><tr><th>Степень поражения</th><th>Площадь</th><th>Доля</th></tr></thead>
        <tbody>
          {result.summary.severity.map((item) => (
            <tr key={item.class_id}>
              <td><i data-severity={item.severity} />{item.label}</td>
              <td>{item.area_ha === null ? "Нет данных" : formatArea(item.area_ha)}</td>
              <td>{item.share === null ? "—" : formatPercent(item.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.coverageGrid}>
        <div><span>AOI</span><strong>{formatArea(result.coverage.query_area_ha)}</strong></div>
        <div><span>Покрытие термоточек</span><strong>{result.coverage.active_fire.status}</strong></div>
        <div><span>Покрытие гарей</span><strong>{result.coverage.burn_scars.status}</strong></div>
      </div>

      <div className={styles.exportActions}>
        <button type="button" onClick={() => download("contours")} disabled={downloading !== null}>
          <Download size={15} />{downloading === "contours" ? "Готовим…" : "Скачать контуры · GeoJSON"}
        </button>
        <button type="button" onClick={() => download("csv")} disabled={downloading !== null}>
          <Download size={15} />{downloading === "csv" ? "Готовим…" : "Скачать справку · CSV"}
        </button>
        <button type="button" className={styles.quietButton} onClick={() => download("json")} disabled={downloading !== null}>
          <FileJson size={15} />JSON
        </button>
      </div>
      {downloadError && <p className={styles.downloadError} role="alert">{downloadError}</p>}

      <details className={styles.methodDetails}>
        <summary><Info size={14} />Как рассчитано</summary>
        <dl>
          <div><dt>Правило дат</dt><dd>Гари отобраны по дате послепожарной съёмки; это не дата начала пожара.</dd></div>
          <div><dt>Площадь</dt><dd>{result.calculation.area_method}. CRS: {result.calculation.area_crs}.</dd></div>
          <div><dt>Обрезка</dt><dd>{result.calculation.clipping_rule}.</dd></div>
          <div><dt>Повторные оценки</dt><dd>{result.calculation.deduplication_rule}.</dd></div>
          <div><dt>Набор</dt><dd>{result.request.dataset_id}@{result.request.dataset_version}, обработка {result.provenance.processing_version}.</dd></div>
          <div><dt>Сцены</dt><dd>{result.provenance.scene_ids.join(", ") || "Не указаны"}.</dd></div>
          <div><dt>Result ID</dt><dd className="mono">{result.result_id}</dd></div>
        </dl>
      </details>
    </section>
  );
}
