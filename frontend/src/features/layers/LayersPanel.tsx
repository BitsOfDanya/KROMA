"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";

import { IconButton } from "@/components/ui/IconButton";
import overviewStyles from "@/features/overview/overview.module.css";
import { useWorkspace, type BasemapMode, type LayerId } from "@/state/workspace";

import styles from "./layers.module.css";

const BASEMAPS: { value: BasemapMode; label: string; thumb: string }[] = [
  { value: "map", label: "Карта", thumb: "linear-gradient(135deg, var(--map-land) 0 55%, var(--map-water) 55% 70%, var(--map-forest) 70%)" },
  { value: "satellite", label: "Спутник", thumb: "linear-gradient(135deg, #2f3b2a 0 40%, #5b5a45 40% 60%, #1f3340 60%)" },
  { value: "terrain", label: "Рельеф", thumb: "repeating-linear-gradient(120deg, var(--map-hillshade-accent) 0 6px, var(--map-land) 6px 12px)" },
];

interface LayerRow {
  id: LayerId;
  label: string;
  hint?: string;
  glyph: ReactNode;
}

const line = (color: string, dashed = false) => (
  <svg width="20" height="10" aria-hidden="true">
    <line x1="1" y1="5" x2="19" y2="5" stroke={color} strokeWidth="2.2" strokeDasharray={dashed ? "2 2" : undefined} strokeLinecap="round" />
  </svg>
);
const fill = (color: string, opacity = 0.3, dashed = false) => (
  <svg width="20" height="12" aria-hidden="true">
    <rect x="1" y="1" width="18" height="10" rx="2" fill={color} fillOpacity={opacity} stroke={color} strokeDasharray={dashed ? "2 2" : undefined} />
  </svg>
);
const dot = (color: string, ring = false) => (
  <svg width="20" height="14" aria-hidden="true">
    {ring ? <circle cx="10" cy="7" r="5" fill="none" stroke={color} strokeWidth="1.4" /> : <circle cx="10" cy="7" r="3.5" fill={color} />}
  </svg>
);

const GROUPS: { title: string; rows: LayerRow[] }[] = [
  {
    title: "Пожары",
    rows: [
      { id: "incidents", label: "События", hint: "Объединённые детекции KROMA", glyph: dot("var(--incident-critical)") },
      { id: "rawDetections", label: "Сырые детекции", hint: "VIIRS и MODIS за 7 суток", glyph: dot("var(--observation)") },
      { id: "burnScars", label: "Гари", glyph: fill("var(--burn-scar)", 0.4) },
      { id: "perimeter", label: "Периметр", glyph: fill("var(--incident-high)", 0.15) },
      { id: "activeFront", label: "Активная кромка", glyph: line("var(--incident-critical)") },
      {
        id: "thermalMemory",
        label: "Thermal Memory",
        hint: "Постоянные тепловые источники",
        glyph: (
          <svg width="20" height="14" aria-hidden="true">
            <path d="M10 2 L15 7 L10 12 L5 7 Z" fill="none" stroke="var(--thermal-source)" strokeWidth="1.4" />
          </svg>
        ),
      },
    ],
  },
  {
    title: "Прогноз · выбранное событие",
    rows: [
      { id: "forecastP50", label: "P50", hint: "Наиболее вероятная зона", glyph: fill("var(--forecast-50)", 0.35) },
      { id: "forecastP80", label: "P80", glyph: fill("var(--forecast-80)", 0.22) },
      { id: "forecastP95", label: "P95", hint: "Граница неопределённости", glyph: fill("var(--forecast-95)", 0.12, true) },
    ],
  },
  {
    title: "Контекст",
    rows: [
      { id: "settlements", label: "Населённые пункты", glyph: dot("var(--text)", true) },
      { id: "roads", label: "Дороги", glyph: line("var(--infrastructure)") },
      { id: "infrastructure", label: "Инфраструктура и ЛЭП", glyph: line("var(--infrastructure)", true) },
      { id: "protectedAreas", label: "ООПТ", glyph: fill("var(--protected-area)", 0.12, true) },
    ],
  },
  {
    title: "Среда",
    rows: [
      {
        id: "wind",
        label: "Ветер",
        glyph: (
          <svg width="20" height="14" aria-hidden="true">
            <path d="M3 7 H16 M12 3.5 L16 7 L12 10.5" fill="none" stroke="var(--wind)" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        ),
      },
      { id: "clouds", label: "Облачность", hint: "Вероятность на ближайший пролёт", glyph: fill("var(--cloud)", 0.3, true) },
    ],
  },
];

export function LayerToggle({ row }: { row: LayerRow }) {
  const active = useWorkspace((state) => state.layers[row.id]);
  const toggle = useWorkspace((state) => state.toggleLayer);
  return (
    <button type="button" role="switch" aria-checked={active} className={styles.toggle} onClick={() => toggle(row.id)}>
      {row.glyph}
      <span>
        {row.label}
        {row.hint && <span className={styles.toggleHint}>{row.hint}</span>}
      </span>
      <span className={styles.switch} aria-hidden="true" />
    </button>
  );
}

export function LayersPanel() {
  const basemap = useWorkspace((state) => state.basemap);
  const setBasemap = useWorkspace((state) => state.setBasemap);
  const closePanel = useWorkspace((state) => state.closePanel);

  return (
    <section className={overviewStyles.panel} aria-labelledby="layers-title">
      <header className={overviewStyles.panelHeader}>
        <h2 id="layers-title" className={overviewStyles.panelTitle}>
          Слои
        </h2>
        <span style={{ flex: 1 }} />
        <IconButton label="Закрыть панель" size="sm" showTooltip={false} icon={<X size={15} />} onClick={closePanel} />
      </header>
      <div className={overviewStyles.panelBody}>
        <div className={styles.group}>
          <h3 className={styles.groupTitle}>Основа</h3>
          <div className={styles.basemaps} role="radiogroup" aria-label="Подложка">
            {BASEMAPS.map((item) => (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={basemap === item.value}
                className={styles.basemap}
                onClick={() => setBasemap(item.value)}
              >
                <span className={styles.thumb} style={{ background: item.thumb }} />
                {item.label}
              </button>
            ))}
          </div>
        </div>
        {GROUPS.map((group) => (
          <div key={group.title} className={styles.group}>
            <h3 className={styles.groupTitle}>{group.title}</h3>
            {group.rows.map((row) => (
              <LayerToggle key={row.id} row={row} />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
