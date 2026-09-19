"use client";

import {
  Database,
  ExternalLink,
  Flame,
  Layers,
  MapPinned,
  Search,
  Satellite,
  Wind,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { exampleDraft, querySearch } from "@/features/analysis/query";
import { useAnalysisDatasets, useMlStatus, useOverview, useTrainChips } from "@/lib/api/queries";
import type { TrainChip, TrainChipKind } from "@/lib/api/types";
import { useWorkspace, type LayerId } from "@/state/workspace";

import { ChipInspector } from "./ChipInspector";
import styles from "./explorer.module.css";

const LAYER_PRESETS: {
  id: string;
  label: string;
  hint: string;
  layers: Partial<Record<LayerId, boolean>>;
  basemap?: "map" | "satellite" | "terrain";
  profile?: "ops" | "fireWeather";
  region?: string;
}[] = [
  {
    id: "aoi",
    label: "Территория мониторинга",
    hint: "АОИ Нижнее Поволжье и Подонье · зоны UTM",
    layers: { monitoringAoi: true, incidents: true, rawDetections: false },
    region: "aoi",
  },
  {
    id: "train",
    label: "Official TRAIN footprints",
    hint: "AF / BS чипы на карте · клик → Dataset Inspector",
    layers: { monitoringChips: true, monitoringAoi: true, incidents: false, burnScars: false },
    region: "aoi",
  },
  {
    id: "raw",
    label: "Сырые термоточки",
    hint: "VIIRS / FIRMS детекции без объединения в события",
    layers: { rawDetections: true, incidents: true, burnScars: false, wind: false, clouds: false },
  },
  {
    id: "active",
    label: "Активное горение",
    hint: "События, кромка и периметр",
    layers: { incidents: true, rawDetections: false, activeFront: true, perimeter: true, burnScars: false },
  },
  {
    id: "burn",
    label: "Гари и severity",
    hint: "Контуры гарей поверх спутниковой подложки",
    layers: { burnScars: true, incidents: true, activeFront: false, wind: false },
    basemap: "satellite",
  },
  {
    id: "weather",
    label: "Погодный контекст",
    hint: "Ветер, облачность, рельеф и очаги",
    layers: {},
    profile: "fireWeather",
  },
  {
    id: "terrain",
    label: "Рельеф / DEM",
    hint: "Подложка с hillshade",
    layers: { wind: false, clouds: false },
    basemap: "terrain",
  },
];

const ORIGIN = {
  model_output: "Результат модели",
  reference: "Эталон",
  synthetic_demo: "Синтетический пример",
} as const;

function chipHref(chipId: string) {
  return `/explorer?chip=${encodeURIComponent(chipId)}`;
}

function TrainChipRow({ chip }: { chip: TrainChip }) {
  return (
    <li>
      <div>
        <strong className="mono">{chip.chip_id}</strong>
        <span className={styles.meta}>
          {chip.kind === "af"
            ? `${chip.satellite ?? "VIIRS"} · ${chip.acq_datetime?.slice(0, 10) ?? "—"} · ${chip.has_fire ? "has fire" : "no fire"} · ${chip.n_fire_px ?? 0} px`
            : `${chip.fire_event_id ?? "—"} · ${chip.date_pre ?? "?"} → ${chip.date_post ?? "?"} · ${chip.burn_area_ha ?? "—"} га`}
        </span>
        <p>
          OFFICIAL TRAIN · EPSG:{chip.epsg ?? "—"} · GSD {chip.gsd_m ?? "—"} м
          {chip.cloud_frac != null ? ` · cloud ${(chip.cloud_frac * 100).toFixed(1)}%` : ""}
        </p>
      </div>
      <Link className={styles.ghostLink} href={chipHref(chip.chip_id)}>
        Inspector
      </Link>
    </li>
  );
}

export function ExplorerView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedChip = searchParams.get("chip");

  const catalog = useAnalysisDatasets();
  const overview = useOverview();
  const ml = useMlStatus();
  const [regionId, setRegionId] = useState<string>("");
  const [trainKind, setTrainKind] = useState<TrainChipKind>("bs");
  const [hasFire, setHasFire] = useState<"all" | "yes" | "no">("all");
  const [query, setQuery] = useState("");

  const train = useTrainChips({
    kind: trainKind,
    has_fire: trainKind === "af" ? (hasFire === "all" ? undefined : hasFire === "yes") : undefined,
    q: query.trim() || undefined,
    limit: 80,
  });

  const setMapProfile = useWorkspace((state) => state.setMapProfile);
  const setBasemap = useWorkspace((state) => state.setBasemap);
  const setLayer = useWorkspace((state) => state.setLayer);
  const setEvidenceMode = useWorkspace((state) => state.setEvidenceMode);
  const setRegion = useWorkspace((state) => state.setRegion);

  const regions = overview.data?.regions ?? [];
  const datasets = catalog.data?.items;

  const applyPreset = (presetId: string) => {
    const preset = LAYER_PRESETS.find((item) => item.id === presetId);
    if (!preset) return;
    if (preset.profile === "fireWeather") {
      setMapProfile("fireWeather");
    } else {
      setMapProfile("ops");
      if (preset.basemap) setBasemap(preset.basemap);
      Object.entries(preset.layers).forEach(([id, visible]) => setLayer(id as LayerId, Boolean(visible)));
      if (preset.layers.rawDetections) setEvidenceMode("data");
      else setEvidenceMode("events");
    }
    const nextRegion = preset.region || regionId;
    if (nextRegion) {
      setRegionId(nextRegion);
      setRegion(nextRegion);
    }
  };

  const analysisHref = useMemo(() => {
    const first = datasets?.[0];
    if (!first) return "/analytics?tab=area";
    const draft = exampleDraft(first);
    const params = new URLSearchParams({
      tab: "area",
      dataset: draft.datasetId,
      version: draft.datasetVersion,
      west: draft.west,
      south: draft.south,
      east: draft.east,
      north: draft.north,
      from: draft.from,
      to: draft.to,
    });
    return `/analytics?${params.toString()}`;
  }, [datasets]);

  if (selectedChip) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <PageHeader
            title="Dataset Inspector"
            description="Official TRAIN chip · competition test на карту не выводится."
          />
          <ChipInspector chipId={selectedChip} onClose={() => router.push("/explorer")} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Данные и слои"
          description="Official TRAIN, prepared demo и реальные геопривязанные сцены. Competition test без геопривязки не показывается."
          actions={
            <Link className={styles.primaryLink} href={analysisHref}>
              <MapPinned size={15} />
              Анализ территории
            </Link>
          }
        />

        <Card className={styles.panel + " " + styles.trainPanel}>
          <div className={styles.panelHead}>
            <Database size={16} />
            <div>
              <h2>OFFICIAL TRAIN DATASET</h2>
              <p>
                {train.data
                  ? `${train.data.counts.af} AF · ${train.data.counts.bs} BS · footprints на карте`
                  : "Индекс train-чипов из GeoTIFF transform → WGS84"}
              </p>
            </div>
          </div>

          <div className={styles.trainFilters}>
            <div className={styles.modeToggle} role="tablist" aria-label="AF / BS">
              {(["af", "bs"] as const).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  role="tab"
                  aria-selected={trainKind === kind}
                  data-active={trainKind === kind}
                  onClick={() => setTrainKind(kind)}
                >
                  {kind.toUpperCase()}
                </button>
              ))}
            </div>

            {trainKind === "af" && (
              <label className={styles.field}>
                Fire
                <select
                  value={hasFire}
                  onChange={(event) => setHasFire(event.target.value as typeof hasFire)}
                  aria-label="Has fire"
                >
                  <option value="all">Все</option>
                  <option value="yes">Has fire</option>
                  <option value="no">No fire</option>
                </select>
              </label>
            )}

            <label className={styles.field + " " + styles.searchField}>
              Поиск
              <span className={styles.searchBox}>
                <Search size={14} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="chip_id / event / satellite"
                  aria-label="Поиск chip"
                />
              </span>
            </label>

            <button
              type="button"
              className={styles.ghostLink}
              onClick={() => {
                applyPreset("train");
                router.push("/");
              }}
            >
              <MapPinned size={14} />
              Footprints на карте
            </button>
          </div>

          {(ml.data || ml.isPending) && (
            <div className={styles.mlStrip}>
              <span data-ready={ml.data?.af.ready ?? false}>AF {ml.data?.af.ready ? "ready" : "GT only"}</span>
              <span data-ready={ml.data?.bs.ready ?? false}>BS {ml.data?.bs.ready ? "ready" : "GT only"}</span>
              <em>{ml.data?.note ?? "Проверяем ml/artifacts…"}</em>
            </div>
          )}

          {train.data && !train.data.available && (
            <StateMessage
              title="Снимки TRAIN пока недоступны"
              detail="Метаданные доступны, исходные TIFF ещё не подключены на сервере."
            />
          )}
          {train.isPending && <p className={styles.muted}>Загружаем индекс TRAIN…</p>}
          {train.isError && <ErrorMessage error={train.error} onRetry={() => train.refetch()} />}
          {train.data && train.data.items.length === 0 && (
            <StateMessage title="Нет чипов" detail="Смените фильтр или пересоберите train_chips_index." />
          )}
          {train.data && train.data.items.length > 0 && (
            <>
              <p className={styles.muted}>
                Показано {train.data.items.length} из {train.data.total}
              </p>
              <ul className={styles.list + " " + styles.trainList}>
                {train.data.items.map((chip) => (
                  <TrainChipRow key={chip.chip_id} chip={chip} />
                ))}
              </ul>
            </>
          )}
        </Card>

        <div className={styles.grid}>
          <Card className={styles.panel}>
            <div className={styles.panelHead}>
              <MapPinned size={16} />
              <div>
                <h2>Территория мониторинга</h2>
                <p>АОИ · DEMO REAL/PREPARED · не competition test</p>
              </div>
            </div>
            <ul className={styles.list}>
              <li>
                <div>
                  <strong>Нижнее Поволжье и Подонье</strong>
                  <span className={styles.meta}>~435 тыс. км² · EPSG:4326 · сезоны 2019–2025 · месяцы 04–10</span>
                  <p>
                    Ростовская, Волгоградская, Астраханская обл., запад и центр Саратовской обл., Республика Калмыкия.
                    На карте — граница АОИ, полосы UTM и footprints train-чипов.
                  </p>
                </div>
                <div className={styles.stackActions}>
                  <button
                    type="button"
                    className={styles.ghostLink}
                    onClick={() => {
                      setRegionId("aoi");
                      setRegion("aoi");
                      setLayer("monitoringAoi", true);
                      setLayer("monitoringChips", true);
                    }}
                  >
                    Показать на карте
                  </button>
                  <a
                    className={styles.ghostLink}
                    href="https://disk.yandex.ru/d/-rpmevTflbXZQg"
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={14} />
                    Источник
                  </a>
                </div>
              </li>
            </ul>
          </Card>

          <Card className={styles.panel}>
            <div className={styles.panelHead}>
              <Database size={16} />
              <div>
                <h2>Подготовленные наборы</h2>
                <p>DEMO / REAL / PREPARED · только геопривязанные</p>
              </div>
            </div>
            {catalog.isPending && <p className={styles.muted}>Загружаем каталог…</p>}
            {catalog.isError && <ErrorMessage error={catalog.error} onRetry={() => catalog.refetch()} />}
            {catalog.data && (datasets?.length ?? 0) === 0 && (
              <StateMessage title="Нет наборов" detail="Проверьте KROMA_PREPARED_DATA_PATH и readiness." />
            )}
            <ul className={styles.list}>
              {(datasets ?? []).map((item) => (
                <li key={`${item.dataset_id}@${item.dataset_version}`}>
                  <div>
                    <strong>{item.name}</strong>
                    <span className={styles.meta}>
                      {ORIGIN[item.origin]} · {item.dataset_id}@{item.dataset_version}
                    </span>
                    <p>{item.description}</p>
                    {item.scene_ids.length > 0 && (
                      <span className={styles.meta}>Сцены: {item.scene_ids.join(", ")}</span>
                    )}
                  </div>
                  <Link
                    className={styles.ghostLink}
                    href={`/analytics?${querySearch({
                      datasetId: item.dataset_id,
                      datasetVersion: item.dataset_version,
                      bbox: item.example.bbox,
                      from: item.example.from,
                      to: item.example.to,
                    })}`}
                  >
                    Открыть расчёт
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className={styles.grid}>
          <Card className={styles.panel}>
            <div className={styles.panelHead}>
              <Layers size={16} />
              <div>
                <h2>Слои на карте</h2>
                <p>Пресеты без выдуманных снимков — только то, что уже в сервисе</p>
              </div>
            </div>
            <label className={styles.field}>
              Регион / AOI
              <select value={regionId} onChange={(event) => setRegionId(event.target.value)} aria-label="Регион">
                <option value="">Все регионы</option>
                {regions.map((region) => (
                  <option key={region.id} value={region.id}>
                    {region.name}
                  </option>
                ))}
              </select>
            </label>
            <div className={styles.presets}>
              {LAYER_PRESETS.map((preset) => (
                <button key={preset.id} type="button" className={styles.preset} onClick={() => applyPreset(preset.id)}>
                  <span className={styles.presetIcon}>
                    {preset.id === "aoi" || preset.id === "train" ? (
                      <MapPinned size={16} />
                    ) : preset.id === "weather" ? (
                      <Wind size={16} />
                    ) : preset.id === "burn" ? (
                      <Satellite size={16} />
                    ) : (
                      <Flame size={16} />
                    )}
                  </span>
                  <span>
                    <strong>{preset.label}</strong>
                    <em>{preset.hint}</em>
                  </span>
                </button>
              ))}
            </div>
            <Link className={styles.ghostLink} href="/">
              Открыть карту с пресетом
            </Link>
          </Card>

          <Card className={styles.panel}>
            <div className={styles.panelHead}>
              <Satellite size={16} />
              <div>
                <h2>Граница сервиса</h2>
                <p>Что намеренно не подключено</p>
              </div>
            </div>
            <ul className={styles.list}>
              <li>
                <div>
                  <strong>Competition TEST</strong>
                  <span className={styles.meta}>Анонимизирован · без координат</span>
                  <p>
                    Не геопривязываем, не восстанавливаем координаты, не показываем на карте. Только official TRAIN +
                    prepared/demo сцены.
                  </p>
                </div>
              </li>
              <li>
                <div>
                  <strong>ML weights</strong>
                  <span className={styles.meta}>ml/artifacts</span>
                  <p>
                    GOLD v006 подключён через единый адаптер. Inspector показывает GT, before/after, prediction и ошибки; при отсутствии весов выводится причина недоступности.
                  </p>
                </div>
              </li>
            </ul>
          </Card>
        </div>

        <Card className={styles.footerCard}>
          <div>
            <h2>Обязательный сценарий</h2>
            <p>
              Территория → период → данные → результат: термоточки, контуры, severity, площадь, экспорт GeoJSON/CSV/JSON
              и REST.
            </p>
          </div>
          <div className={styles.footerActions}>
            <Link className={styles.primaryLink} href={analysisHref}>
              Запустить анализ
            </Link>
            <a
              className={styles.ghostLink}
              href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}/docs`}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={14} />
              Swagger API
            </a>
            <Link className={styles.ghostLink} href="/about">
              О проекте
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
