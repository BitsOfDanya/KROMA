"use client";

import { Database, ExternalLink, Flame, Layers, MapPinned, Satellite, Wind } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorMessage, StateMessage } from "@/components/ui/StateMessage";
import { useAnalysisDatasets, useOverview } from "@/lib/api/queries";
import { exampleDraft, querySearch } from "@/features/analysis/query";
import { useWorkspace, type LayerId } from "@/state/workspace";

import styles from "./explorer.module.css";

const LAYER_PRESETS: { id: string; label: string; hint: string; layers: Partial<Record<LayerId, boolean>>; basemap?: "map" | "satellite" | "terrain"; profile?: "ops" | "fireWeather"; region?: string }[] = [
  {
    id: "aoi",
    label: "Территория мониторинга",
    hint: "АОИ Нижнее Поволжье и Подонье · зоны UTM",
    layers: { monitoringAoi: true, incidents: true, rawDetections: false },
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

export function ExplorerView() {
  const catalog = useAnalysisDatasets();
  const overview = useOverview();
  const [regionId, setRegionId] = useState<string>("");
  const setMapProfile = useWorkspace((state) => state.setMapProfile);
  const setBasemap = useWorkspace((state) => state.setBasemap);
  const setLayer = useWorkspace((state) => state.setLayer);
  const setEvidenceMode = useWorkspace((state) => state.setEvidenceMode);
  const setRegion = useWorkspace((state) => state.setRegion);

  const regions = overview.data?.regions ?? [];
  const datasets = catalog.data?.items ?? [];

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
    const first = datasets[0];
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

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <PageHeader
          title="Данные и слои"
          description="Выберите источник, территорию и набор слоёв. Competition test без геопривязки сюда не подключены."
          actions={
            <Link className={styles.primaryLink} href={analysisHref}>
              <MapPinned size={15} />
              Анализ территории
            </Link>
          }
        />

        <div className={styles.grid}>
          <Card className={styles.panel}>
            <div className={styles.panelHead}>
              <MapPinned size={16} />
              <div>
                <h2>Территория мониторинга</h2>
                <p>Из датасета Мониторинг DATA · не ML-чипы</p>
              </div>
            </div>
            <ul className={styles.list}>
              <li>
                <div>
                  <strong>Нижнее Поволжье и Подонье</strong>
                  <span className={styles.meta}>~435 тыс. км² · EPSG:4326 · сезоны 2019–2025 · месяцы 04–10</span>
                  <p>
                    Ростовская, Волгоградская, Астраханская обл., запад и центр Саратовской обл., Республика Калмыкия.
                    На карте — граница АОИ, полосы UTM и footprints train-чипов (слой «Чипы датасета»).
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
                <p>Только геопривязанные train / demo / real dataset</p>
              </div>
            </div>
            {catalog.isPending && <p className={styles.muted}>Загружаем каталог…</p>}
            {catalog.isError && <ErrorMessage error={catalog.error} onRetry={() => catalog.refetch()} />}
            {catalog.data && datasets.length === 0 && (
              <StateMessage title="Нет наборов" detail="Проверьте KROMA_PREPARED_DATA_PATH и readiness." />
            )}
            <ul className={styles.list}>
              {datasets.map((item) => (
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
                    {preset.id === "aoi" ? (
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
                <h2>Что не подключено</h2>
                <p>Честная граница сервиса</p>
              </div>
            </div>
            <ul className={styles.list}>
              <li>
                <div>
                  <strong>fire-train / fire-test tar</strong>
                  <span className={styles.meta}>ML-чипы AF/BS · Sentinel-1/2 · без live NRT</span>
                  <p>
                    Архивы с Яндекс.Диска — для обучения и инференса. На оперативную карту не выкладываются, пока нет
                    геопривязанного prepared-набора.
                  </p>
                </div>
              </li>
            </ul>
          </Card>
        </div>

        <Card className={styles.footerCard}>
          <div>
            <h2>Обязательный сценарий</h2>
            <p>Территория → период → данные → результат: термоточки, контуры, severity, площадь, экспорт GeoJSON/CSV/JSON и REST.</p>
          </div>
          <div className={styles.footerActions}>
            <Link className={styles.primaryLink} href={analysisHref}>
              Запустить анализ
            </Link>
            <a className={styles.ghostLink} href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? ""}/docs`} target="_blank" rel="noreferrer">
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
