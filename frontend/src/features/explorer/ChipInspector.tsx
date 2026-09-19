"use client";

/* Dynamic API / data-URI previews — next/image is not useful here. */
/* eslint-disable @next/next/no-img-element */

import { ArrowLeft, Layers, Satellite, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { api } from "@/lib/api/endpoints";
import { useMlStatus, useTrainChip } from "@/lib/api/queries";
import type { TrainAsset, TrainChip } from "@/lib/api/types";

import styles from "./chipInspector.module.css";

type AfMode = "ground_truth" | "prediction" | "difference";
type BsCompare = "ground_truth" | "model" | "errors";
type BsLayer = "none" | "mask" | "aux";

function pct(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function num(value: number | null | undefined, digits = 1) {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU", { maximumFractionDigits: digits });
}

function severityShares(chip: TrainChip) {
  const s1 = chip.sev1_px ?? 0;
  const s2 = chip.sev2_px ?? 0;
  const s3 = chip.sev3_px ?? 0;
  const total = s1 + s2 + s3;
  if (total <= 0) return null;
  return {
    low: (s1 / total) * 100,
    moderate: (s2 / total) * 100,
    high: (s3 / total) * 100,
    total,
  };
}

function BeforeAfterSlider({
  chipId,
  showSeverity,
}: {
  chipId: string;
  showSeverity: boolean;
}) {
  const [pos, setPos] = useState(50);
  const pre = api.datasets.previewUrl(chipId, "s2_pre", 640);
  const post = api.datasets.previewUrl(chipId, "s2_post", 640);
  const mask = api.datasets.previewUrl(chipId, "mask", 640);

  return (
    <div className={styles.sliderWrap}>
      <div className={styles.sliderStage}>
        <img className={styles.sliderBase} src={post} alt="Sentinel-2 после пожара" />
        <div className={styles.sliderBefore} style={{ width: `${pos}%` }}>
          <img src={pre} alt="Sentinel-2 до пожара" style={{ width: `${10000 / Math.max(pos, 1)}%` }} />
        </div>
        {showSeverity && (
          <img className={styles.severityOverlay} src={mask} alt="GT severity" />
        )}
        <div className={styles.sliderHandle} style={{ left: `${pos}%` }} />
        <span className={styles.sliderTag} data-side="before">
          BEFORE
        </span>
        <span className={styles.sliderTag} data-side="after">
          AFTER
        </span>
      </div>
      <label className={styles.sliderControl}>
        <span>До ←→ После</span>
        <input
          type="range"
          min={0}
          max={100}
          value={pos}
          onChange={(event) => setPos(Number(event.target.value))}
          aria-label="Before / After"
        />
      </label>
    </div>
  );
}

function AssetThumb({ chipId, asset, label }: { chipId: string; asset: TrainAsset; label: string }) {
  return (
    <figure className={styles.thumb}>
      <img src={api.datasets.previewUrl(chipId, asset, 320)} alt={label} />
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function AfInspector({ chip }: { chip: TrainChip }) {
  const ml = useMlStatus();
  const [mode, setMode] = useState<AfMode>("ground_truth");
  const predictionReady = Boolean(ml.data?.af.ready && chip.inspector?.prediction_available);

  return (
    <div className={styles.inspectorBody}>
      <div className={styles.modeRow} role="tablist" aria-label="Режим AF">
        {(
          [
            ["ground_truth", "Эталон"],
            ["prediction", "Предсказание"],
            ["difference", "Ошибки"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={mode === id}
            className={styles.modeBtn}
            data-active={mode === id}
            onClick={() => setMode(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={styles.viewerGrid}>
        {mode === "ground_truth" && (
          <>
            <AssetThumb chipId={chip.chip_id} asset="viirs" label="VIIRS I1–I5" />
            <AssetThumb chipId={chip.chip_id} asset="mask" label="GT mask" />
            <AssetThumb chipId={chip.chip_id} asset="aux" label="AUX" />
          </>
        )}
        {mode === "prediction" && (
          <div className={styles.notice}>
            {predictionReady ? (
              <p>AF prediction overlay будет здесь после монтирования весов.</p>
            ) : (
              <p>
                Веса LightGBM AF не смонтированы (`ml/artifacts/af/lightgbm.joblib`). Показан только official TRAIN
                ground truth. {chip.inspector?.prediction_note}
              </p>
            )}
            <AssetThumb chipId={chip.chip_id} asset="mask" label="GT (reference)" />
          </div>
        )}
        {mode === "difference" && (
          <div className={styles.notice}>
            <p>
              TP / FP / FN появятся после инференса. Пока доступен только эталон:{" "}
              <strong>{num(chip.n_fire_px, 0)}</strong> fire px · valid {pct(chip.valid_frac)}.
            </p>
            <div className={styles.legendCompact}>
              <span data-tone="tp">TP</span>
              <span data-tone="fp">FP</span>
              <span data-tone="fn">FN</span>
            </div>
          </div>
        )}
      </div>

      <dl className={styles.metrics}>
        <div>
          <dt>Precision / Recall / F1</dt>
          <dd>н/д без prediction</dd>
        </div>
        <div>
          <dt>n_fire_px</dt>
          <dd>{num(chip.n_fire_px, 0)}</dd>
        </div>
        <div>
          <dt>valid_frac</dt>
          <dd>{pct(chip.valid_frac)}</dd>
        </div>
      </dl>
    </div>
  );
}

function BsInspector({ chip }: { chip: TrainChip }) {
  const ml = useMlStatus();
  const [compare, setCompare] = useState<BsCompare>("ground_truth");
  const [layer, setLayer] = useState<BsLayer>("mask");
  const shares = severityShares(chip);
  const predictionReady = Boolean(ml.data?.bs.ready && chip.inspector?.prediction_available);

  return (
    <div className={styles.inspectorBody}>
      <BeforeAfterSlider chipId={chip.chip_id} showSeverity={layer === "mask"} />

      <div className={styles.modeRow} role="tablist" aria-label="GT vs Model">
        {(
          [
            ["ground_truth", "Эталон"],
            ["model", "Модель"],
            ["errors", "Ошибки"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={compare === id}
            className={styles.modeBtn}
            data-active={compare === id}
            onClick={() => setCompare(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className={styles.layerRow}>
        <span>Слои</span>
        {(
          [
            ["none", "Только S2"],
            ["mask", "GT severity"],
            ["aux", "AUX / physics"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={styles.chipBtn}
            data-active={layer === id}
            onClick={() => setLayer(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {compare !== "ground_truth" && !predictionReady && (
        <div className={styles.notice}>
          <ShieldAlert size={16} />
          <p>
            BS GOLD/v004 веса не смонтированы — IoU и prediction overlay недоступны. Эталон severity и before/after
            работают на official TRAIN.
          </p>
        </div>
      )}

      <div className={styles.splitRow}>
        <div>
          <h3>Severity</h3>
          <div className={styles.legendSeverity}>
            <span data-sev="1">Low</span>
            <span data-sev="2">Moderate</span>
            <span data-sev="3">High</span>
          </div>
          {shares ? (
            <p className={styles.metaLine}>
              GT composition · Low {shares.low.toFixed(0)}% · Moderate {shares.moderate.toFixed(0)}% · High{" "}
              {shares.high.toFixed(0)}%
            </p>
          ) : (
            <p className={styles.metaLine}>Нет burn pixels в маске</p>
          )}
          <dl className={styles.metrics}>
            <div>
              <dt>Burn area (GT)</dt>
              <dd>{num(chip.burn_area_ha)} га</dd>
            </div>
            <div>
              <dt>IoU burn / class / mIoU</dt>
              <dd>н/д без prediction</dd>
            </div>
          </dl>
        </div>

        <aside className={styles.explain}>
          <h3>Почему участок повреждён</h3>
          <p className={styles.explainHint}>Фактические признаки сцены — не сгенерированный текст.</p>
          <dl>
            <div>
              <dt>Burn area (GT)</dt>
              <dd>{num(chip.burn_area_ha)} га</dd>
            </div>
            <div>
              <dt>Cloud / valid</dt>
              <dd>
                {pct(chip.cloud_frac)} / {pct(chip.valid_frac)}
              </dd>
            </div>
            <div>
              <dt>Severity px (1/2/3)</dt>
              <dd>
                {num(chip.sev1_px, 0)} / {num(chip.sev2_px, 0)} / {num(chip.sev3_px, 0)}
              </dd>
            </div>
            <div>
              <dt>Neural prediction</dt>
              <dd>{predictionReady ? "готово" : "веса не смонтированы"}</dd>
            </div>
            <div>
              <dt>Physics prior</dt>
              <dd>{predictionReady ? "из pipeline" : "доступен после mount artifacts"}</dd>
            </div>
            <div>
              <dt>Refiner result</dt>
              <dd>{predictionReady ? "LightGBM refiner" : "н/д"}</dd>
            </div>
            <div>
              <dt>Final severity</dt>
              <dd>GT mask 0/1/2/3 (эталон)</dd>
            </div>
          </dl>
          {layer === "aux" && (
            <AssetThumb chipId={chip.chip_id} asset="aux" label="AUX (physics / landcover context)" />
          )}
        </aside>
      </div>
    </div>
  );
}

export function ChipInspector({ chipId, onClose }: { chipId: string; onClose?: () => void }) {
  const chipQuery = useTrainChip(chipId);
  const chip = chipQuery.data;

  const titleMeta = useMemo(() => {
    if (!chip) return "";
    if (chip.kind === "af") {
      return `${chip.satellite ?? "VIIRS"} · ${chip.acq_datetime?.slice(0, 16) ?? "—"} · ${chip.has_fire ? "has fire" : "no fire"}`;
    }
    return `${chip.fire_event_id ?? "—"} · ${chip.date_pre ?? "?"} → ${chip.date_post ?? "?"}`;
  }, [chip]);

  return (
    <Card className={styles.card}>
      <div className={styles.head}>
        <div className={styles.headMain}>
          {onClose ? (
            <button type="button" className={styles.back} onClick={onClose}>
              <ArrowLeft size={15} />К списку
            </button>
          ) : (
            <Link href="/explorer" className={styles.back}>
              <ArrowLeft size={15} />К списку
            </Link>
          )}
          <div>
            <div className={styles.badges}>
              <span data-origin="official_train">OFFICIAL TRAIN</span>
              <span data-kind={chip?.kind ?? "af"}>{(chip?.kind ?? "…").toUpperCase()}</span>
            </div>
            <h2 className="mono">{chipId}</h2>
            <p>{titleMeta}</p>
          </div>
        </div>
        {chip && (
          <div className={styles.headMeta}>
            {chip.kind === "af" ? (
              <>
                <div>
                  <span>valid</span>
                  <strong>{pct(chip.valid_frac)}</strong>
                </div>
                <div>
                  <span>fire px</span>
                  <strong>{num(chip.n_fire_px, 0)}</strong>
                </div>
              </>
            ) : (
              <>
                <div>
                  <span>burn</span>
                  <strong>{num(chip.burn_area_ha)} га</strong>
                </div>
                <div>
                  <span>cloud</span>
                  <strong>{pct(chip.cloud_frac)}</strong>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {chipQuery.isPending && <StateMessage title="Загружаем chip…" detail="Метаданные official TRAIN" />}
      {chipQuery.isError && <ErrorMessage error={chipQuery.error} onRetry={() => chipQuery.refetch()} />}
      {chip && chip.kind === "af" && <AfInspector chip={chip} />}
      {chip && chip.kind === "bs" && <BsInspector chip={chip} />}

      {chip && (
        <div className={styles.foot}>
          <Layers size={14} />
          <span>Assets: {(chip.assets ?? []).join(", ")}</span>
          <Satellite size={14} />
          <span>GSD {chip.gsd_m ?? "—"} м · EPSG:{chip.epsg ?? "—"}</span>
        </div>
      )}
    </Card>
  );
}
