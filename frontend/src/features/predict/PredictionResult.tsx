"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { api } from "@/lib/api/endpoints";
import styles from "./predict.module.css";

const display = (n: number | undefined) =>
  n == null ? "—" : n.toLocaleString("ru-RU", { maximumFractionDigits: 3 });

export function PredictionResult({
  chipId,
  initialLayer = "pred",
}: {
  chipId: string;
  initialLayer?: string;
}) {
  const [layer, setLayer] = useState(initialLayer);
  const query = useQuery({
    queryKey: ["prediction", chipId, "v006"],
    queryFn: ({ signal }) => api.datasets.prediction(chipId, signal),
    staleTime: Infinity,
    retry: false,
  });
  const result = query.data;
  if (query.isPending)
    return (
      <StateMessage
        title="Выполняется inference…"
        detail="Первый запрос включает загрузку моделей; результат кэшируется по версии."
      />
    );
  if (query.isError)
    return <ErrorMessage error={query.error} onRetry={() => query.refetch()} />;
  if (!result || result.status !== "ok")
    return <StateMessage title="Предикт недоступен" detail={result?.detail} />;
  const bs = result.kind === "bs";
  return (
    <Card className={styles.resultCard}>
      <div className={styles.resultHead}>
        <h2>MODEL OUTPUT · {chipId}</h2>
        <span>
          {result.model_version} · {display(result.runtime_ms?.total)} мс
          {result.cache_hit ? " · cache" : ""}
        </span>
      </div>
      <p>{result.prediction?.note}</p>
      <div className={styles.statusRow}>
        {[
          ["gt", "GT"],
          ["pred", "Prediction"],
          ["error", "Errors"],
          ["probability", "Probability"],
        ].map(([id, title]) => (
          <button
            key={id}
            type="button"
            className={styles.ghostLink}
            aria-pressed={layer === id}
            onClick={() => setLayer(id)}
          >
            {title}
          </button>
        ))}
      </div>
      <div className={styles.viewer}>
        <figure>
          <img
            src={api.datasets.previewUrl(chipId, bs ? "s2_post" : "viirs")}
            alt={bs ? "POST" : "VIIRS"}
          />
          <figcaption>{bs ? "POST" : "VIIRS"}</figcaption>
        </figure>
        <figure>
          <img src={api.datasets.overlayUrl(chipId, layer)} alt={layer} />
          <figcaption>
            {layer === "error"
              ? "Красный: FP · синий: FN · жёлтый: severity mismatch · зелёный: AF TP"
              : layer === "gt"
                ? "Official TRAIN GT"
                : "Prediction"}
          </figcaption>
        </figure>
      </div>
      <dl className={styles.metrics}>
        {(bs
          ? [
              ["Burn area, га", result.total_area_ha],
              ["Low, га", result.area_low_ha],
              ["Moderate, га", result.area_moderate_ha],
              ["High, га", result.area_high_ha],
              ["IoU burn", result.metrics?.iou_burn],
              ["mIoU severity", result.metrics?.miou_severity],
            ]
          : [
              ["Fire pixels", result.n_fire_px],
              ["TP", result.metrics?.tp],
              ["FP", result.metrics?.fp],
              ["FN", result.metrics?.fn],
              ["Precision", result.metrics?.precision],
              ["Recall", result.metrics?.recall],
              ["Local F1", result.metrics?.f1],
            ]
        ).map(([label, value]) => (
          <div key={String(label)}>
            <dt>{label}</dt>
            <dd>{display(value as number | undefined)}</dd>
          </div>
        ))}
      </dl>
      {bs && (
        <div className={styles.legendSeverity}>
          <span data-sev="1">Low</span>
          <span data-sev="2">Moderate</span>
          <span data-sev="3">High</span>
        </div>
      )}
      <a
        className={styles.ghostLink}
        href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}/api/v1/datasets/train/${chipId}/rasters`}
      >
        Маски и вероятности · NPZ
      </a>
      {result.polygons.length > 0 || result.thermopoints.length > 0 ? (
        <div className={styles.statusRow}>
          <a
            className={styles.ghostLink}
            href={api.datasets.exportUrl(chipId, "geojson")}
          >
            GeoJSON
          </a>
          <a
            className={styles.ghostLink}
            href={api.datasets.exportUrl(chipId, "shp")}
          >
            Shapefile ZIP
          </a>
        </div>
      ) : (
        <p>Детекций нет: экспорт геометрий пуст.</p>
      )}
    </Card>
  );
}
