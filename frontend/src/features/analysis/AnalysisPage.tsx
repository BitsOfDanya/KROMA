"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Calculator, Database, ExternalLink, MapPinned, RotateCw } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { api } from "@/lib/api/endpoints";
import { useAnalysisDatasets } from "@/lib/api/queries";
import type { AnalysisQuery, AnalysisResult, BBox } from "@/lib/api/types";

import { AnalysisMap } from "./AnalysisMap";
import { AnalysisReport } from "./AnalysisReport";
import styles from "./analysis.module.css";
import {
  EMPTY_DRAFT,
  exampleDraft,
  queryFromSearch,
  querySearch,
  queryToDraft,
  sameQuery,
  validateDraft,
  type AnalysisDraft,
} from "./query";

const ORIGIN = {
  model_output: "Результат модели",
  reference: "Эталон",
  synthetic_demo: "Синтетический пример",
} as const;

function resultQuery(result: AnalysisResult): AnalysisQuery {
  return {
    datasetId: result.request.dataset_id,
    datasetVersion: result.request.dataset_version,
    bbox: result.request.bbox,
    from: result.request.from,
    to: result.request.to,
  };
}

function draftBBox(draft: AnalysisDraft): BBox | null {
  const result = validateDraft({
    ...draft,
    datasetId: draft.datasetId || "draft",
    datasetVersion: draft.datasetVersion || "draft",
    from: draft.from || "2000-01-01",
    to: draft.to || "2000-01-01",
  });
  return result.query?.bbox ?? null;
}

export function AnalysisPage() {
  const searchParams = useSearchParams();
  const applied = useMemo(
    () => queryFromSearch(new URLSearchParams(searchParams.toString())),
    [searchParams],
  );
  return (
    <AnalysisPageState
      key={applied ? querySearch(applied) : "new-analysis"}
      applied={applied}
    />
  );
}

function AnalysisPageState({ applied }: { applied: AnalysisQuery | null }) {
  const router = useRouter();
  const catalog = useAnalysisDatasets();
  const [draft, setDraft] = useState<AnalysisDraft>(() =>
    applied ? queryToDraft(applied) : EMPTY_DRAFT,
  );
  const [errors, setErrors] = useState<Partial<Record<keyof AnalysisDraft | "bbox", string>>>({});

  const analysis = useQuery({
    queryKey: ["analysis", "run", applied],
    queryFn: ({ signal }) => api.analysis.run(applied as AnalysisQuery, signal),
    enabled: applied !== null,
    retry: false,
    placeholderData: keepPreviousData,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const effectiveDraft = draft.datasetId || !catalog.data?.items[0]
    ? draft
    : exampleDraft(catalog.data.items[0]);
  const selectedDataset = catalog.data?.items.find(
    (item) => item.dataset_id === effectiveDraft.datasetId && item.dataset_version === effectiveDraft.datasetVersion,
  );
  const draftQuery = validateDraft(effectiveDraft).query;
  const parametersChanged = Boolean(analysis.data && !sameQuery(draftQuery, resultQuery(analysis.data)));

  const update = (key: keyof AnalysisDraft, value: string) => {
    setDraft((current) => ({ ...(current.datasetId ? current : effectiveDraft), [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined, ...(key === "west" || key === "south" || key === "east" || key === "north" ? { bbox: undefined } : {}) }));
  };

  const setBBox = (bbox: BBox) => {
    setDraft((current) => ({
      ...(current.datasetId ? current : effectiveDraft),
      west: String(Number(bbox[0].toFixed(8))),
      south: String(Number(bbox[1].toFixed(8))),
      east: String(Number(bbox[2].toFixed(8))),
      north: String(Number(bbox[3].toFixed(8))),
    }));
    setErrors((current) => ({ ...current, bbox: undefined }));
  };

  const run = (event: FormEvent) => {
    event.preventDefault();
    const validation = validateDraft(effectiveDraft);
    setErrors(validation.errors);
    if (!validation.query) return;
    router.push(`/analytics?${querySearch(validation.query)}`, { scroll: false });
  };

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Анализ территории"
          description="Один bbox и период для карты, справки и воспроизводимых файлов."
          actions={
            <div className={styles.headerActions}>
              <Link href="/analytics?tab=summary"><ArrowLeft size={14} />Общая аналитика</Link>
              <a href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}/docs`} target="_blank" rel="noreferrer"><ExternalLink size={14} />Swagger API</a>
            </div>
          }
        />

        <div className={styles.workspace}>
          <aside className={styles.queryPanel}>
            <form onSubmit={run} noValidate>
              <div className={styles.formHeading}>
                <Database size={17} />
                <div><h2>Параметры расчёта</h2><p>WGS84 · даты включительно · UTC</p></div>
              </div>

              {catalog.isPending && <p className={styles.inlineState}>Загружаем каталог…</p>}
              {catalog.isError && <ErrorMessage error={catalog.error} onRetry={() => catalog.refetch()} />}
              {catalog.data?.items.length === 0 && (
                <StateMessage title="Нет готовых наборов" detail="Проверьте readiness источника и путь KROMA_PREPARED_DATA_PATH." />
              )}

              {catalog.data && catalog.data.items.length > 0 && (
                <>
                  <label className={styles.fieldLabel}>
                    <span>Подготовленный набор</span>
                    <select
                      value={`${effectiveDraft.datasetId}@${effectiveDraft.datasetVersion}`}
                      onChange={(event) => {
                        const item = catalog.data?.items.find(
                          (candidate) => `${candidate.dataset_id}@${candidate.dataset_version}` === event.target.value,
                        );
                        if (item) setDraft(exampleDraft(item));
                      }}
                      aria-invalid={Boolean(errors.datasetId)}
                    >
                      {catalog.data.items.map((item) => (
                        <option key={`${item.dataset_id}@${item.dataset_version}`} value={`${item.dataset_id}@${item.dataset_version}`}>
                          {item.name} · {item.dataset_version}
                        </option>
                      ))}
                    </select>
                  </label>

                  {selectedDataset && (
                    <div className={styles.datasetInfo}>
                      <span data-origin={selectedDataset.origin}>{ORIGIN[selectedDataset.origin]}</span>
                      <p>{selectedDataset.description}</p>
                      <small>{selectedDataset.available_from} — {selectedDataset.available_to} · {selectedDataset.processing_version}</small>
                      <button type="button" onClick={() => setDraft(exampleDraft(selectedDataset))}>
                        <MapPinned size={14} />Использовать пример
                      </button>
                    </div>
                  )}

                  <fieldset className={styles.bboxFields} aria-describedby="bbox-help bbox-error">
                    <legend>Область: запад, юг, восток, север</legend>
                    {(["west", "south", "east", "north"] as const).map((key) => (
                      <label key={key}>
                        <span>{{ west: "Запад", south: "Юг", east: "Восток", north: "Север" }[key]}</span>
                        <input
                          type="number"
                          step="any"
                          value={effectiveDraft[key]}
                          onChange={(event) => update(key, event.target.value)}
                          aria-invalid={Boolean(errors.bbox)}
                        />
                      </label>
                    ))}
                    <small id="bbox-help">Можно ввести координаты, взять видимую область или выделить её Shift + drag на карте.</small>
                    {errors.bbox && <small id="bbox-error" className={styles.fieldError} role="alert">{errors.bbox}</small>}
                  </fieldset>

                  <div className={styles.dateFields}>
                    <label className={styles.fieldLabel}>
                      <span>С</span>
                      <input type="date" value={effectiveDraft.from} max={effectiveDraft.to || undefined} onChange={(event) => update("from", event.target.value)} aria-invalid={Boolean(errors.from)} />
                      {errors.from && <small className={styles.fieldError}>{errors.from}</small>}
                    </label>
                    <label className={styles.fieldLabel}>
                      <span>По</span>
                      <input type="date" value={effectiveDraft.to} min={effectiveDraft.from || undefined} onChange={(event) => update("to", event.target.value)} aria-invalid={Boolean(errors.to)} />
                      {errors.to && <small className={styles.fieldError}>{errors.to}</small>}
                    </label>
                  </div>

                  <p className={styles.temporalNote}>Гари отбираются по дате послепожарной съёмки; это не дата начала пожара.</p>
                  <button className={styles.runButton} type="submit" disabled={analysis.isFetching || !effectiveDraft.datasetId}>
                    {analysis.isFetching ? <RotateCw size={16} className={styles.spin} /> : <Calculator size={16} />}
                    {analysis.isFetching ? "Рассчитываем…" : "Рассчитать"}
                  </button>
                </>
              )}
            </form>
          </aside>

          <main className={styles.resultColumn}>
            {parametersChanged && (
              <div className={styles.changedNotice} role="status">
                Параметры изменены — карта, справка и экспорт пока относятся к последнему выполненному запросу.
              </div>
            )}
            {analysis.isPlaceholderData && (
              <div className={styles.changedNotice} role="status">Новый расчёт выполняется; ниже временно оставлен предыдущий result_id.</div>
            )}
            {analysis.isError && <ErrorMessage error={analysis.error} onRetry={() => analysis.refetch()} retrying={analysis.isFetching} />}
            {!applied && !analysis.data && (
              <StateMessage
                title="Задайте область и период"
                detail="Используйте готовый пример или измените координаты, затем нажмите «Рассчитать»."
              />
            )}
            <AnalysisMap result={analysis.data ?? null} draftBBox={draftBBox(effectiveDraft)} onDraftBBox={setBBox} />
            {analysis.data && <AnalysisReport result={analysis.data} query={resultQuery(analysis.data)} />}
          </main>
        </div>
      </div>
    </div>
  );
}
