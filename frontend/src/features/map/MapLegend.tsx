"use client";

import { useWorkspace } from "@/state/workspace";

import styles from "./map.module.css";

function FlameGlyph({ tone }: { tone: "critical" | "confirmed" | "watch" }) {
  const color =
    tone === "critical"
      ? "var(--incident-critical)"
      : tone === "confirmed"
        ? "var(--incident-high)"
        : "var(--incident-medium)";
  return (
    <svg width="18" height="20" viewBox="0 0 18 20" aria-hidden="true">
      <path
        d="M9 1.2C11.8 4.2 13.4 6.4 13.1 9.2c-.3 2.4-1.8 4.1-4.1 5.4 1.1-1.5 1.3-2.7.7-3.8C8.8 12.6 7.4 13.8 6.4 15.4 4.6 13.8 3.6 11.8 3.8 9.4 4.1 6.4 6.2 4.1 9 1.2Z"
        fill={color}
      />
    </svg>
  );
}

function IncidentGlyph({
  kind,
}: {
  kind: "suspected" | "confirmed" | "critical";
}) {
  if (kind !== "suspected") {
    return <FlameGlyph tone={kind === "critical" ? "critical" : "confirmed"} />;
  }
  const color = "var(--incident-medium)";
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      <circle
        cx="11"
        cy="11"
        r="6"
        fill="none"
        stroke={color}
        strokeWidth="1.5"
      />
      <circle cx="11" cy="11" r="1.8" fill={color} />
    </svg>
  );
}

function Swatch({
  color,
  opacity = 1,
  dashed,
  line,
}: {
  color: string;
  opacity?: number;
  dashed?: boolean;
  line?: boolean;
}) {
  return (
    <svg width="22" height="12" viewBox="0 0 22 12" aria-hidden="true">
      {line ? (
        <line
          x1="1"
          y1="6"
          x2="21"
          y2="6"
          stroke={color}
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeDasharray={dashed ? "2 2" : undefined}
        />
      ) : (
        <rect
          x="1"
          y="1"
          width="20"
          height="10"
          rx="2"
          fill={color}
          fillOpacity={opacity}
          stroke={color}
          strokeOpacity={0.8}
          strokeDasharray={dashed ? "2 2" : undefined}
        />
      )}
    </svg>
  );
}

function ArrowGlyph() {
  return (
    <svg width="22" height="16" viewBox="0 0 22 16" aria-hidden="true">
      <path
        d="M2 8 H14"
        stroke="var(--wind)"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path d="M11 3.5 L16.5 8 L11 12.5 Z" fill="var(--wind)" />
      <path
        d="M5 5.5 C7 6.2 8.5 7 10 8"
        fill="none"
        stroke="var(--wind)"
        strokeWidth="1.2"
        strokeLinecap="round"
        opacity="0.7"
      />
    </svg>
  );
}

export function MapLegend() {
  const chipId = useWorkspace((state) => state.selectedTrainChipId);
  const trainLayer = useWorkspace((state) => state.trainValidationLayer);
  const evidenceMode = useWorkspace((state) => state.evidenceMode);
  const layers = useWorkspace((state) => state.layers);
  const selected = useWorkspace((state) => state.selectedIncidentId);
  const isReplay = useWorkspace((state) => state.appMode) === "replay";
  const fireWeather =
    useWorkspace((state) => state.mapProfile) === "fireWeather";
  const isAf = chipId?.startsWith("AF_");
  const validationLegend =
    trainLayer === "error"
      ? [
          ["#dc3830", "FP · ложное обнаружение"],
          ["#4884e8", "FN · пропуск"],
          isAf
            ? ["#42be78", "TP · верное обнаружение"]
            : ["#f0be3c", "Ошибка severity"],
        ]
      : isAf
        ? [["var(--incident-critical)", "Пиксель активного огня"]]
        : [
            ["#e8b058", "Low · слабое"],
            ["#e87840", "Moderate · среднее"],
            ["#dc3830", "High · сильное"],
          ];

  return (
    <section className={styles.legend} aria-label="Легенда карты">
      {chipId && (
        <div className={styles.validationControls}>
          {(["gt", "pred", "error"] as const).map((layer) => (
            <button
              key={layer}
              aria-pressed={trainLayer === layer}
              onClick={() =>
                useWorkspace.getState().setTrainValidationLayer(layer)
              }
            >
              {layer.toUpperCase()}
            </button>
          ))}
          <button onClick={() => useWorkspace.getState().selectTrainChip(null)}>
            Снять выбор
          </button>
        </div>
      )}
      {layers.monitoringChips && <div>OFFICIAL TRAIN · AF / BS clusters</div>}
      {chipId && layers.monitoringChips && (
        <>
          <h3 className={styles.legendTitle}>{trainLayer.toUpperCase()}</h3>
          <div className={styles.legendRows}>
            {validationLegend.map(([color, label]) => (
              <div className={styles.legendRow} key={label}>
                <Swatch color={color} opacity={0.55} />
                {label}
              </div>
            ))}
            {trainLayer === "error" && !isAf && (
              <div>Без заливки · верный класс / вне valid</div>
            )}
          </div>
        </>
      )}
      {layers.rawDetections && (
        <div>RAW · {isReplay ? "SCENARIO" : "NASA FIRMS"}</div>
      )}
      <h3 className={styles.legendTitle}>
        {fireWeather
          ? "Погодный контекст"
          : evidenceMode === "events"
            ? "События"
            : "Спутниковые детекции"}
      </h3>
      {evidenceMode === "events" ? (
        <div className={styles.legendRows}>
          <div className={styles.legendRow}>
            <IncidentGlyph kind="critical" />
            Критическое горение
          </div>
          <div className={styles.legendRow}>
            <IncidentGlyph kind="confirmed" />
            Подтверждённый очаг
          </div>
          <div className={styles.legendRow}>
            <IncidentGlyph kind="suspected" />
            Предварительный
          </div>
          {isReplay && layers.activeFront && (
            <div className={styles.legendRow}>
              <Swatch color="var(--incident-critical)" line />
              Активная кромка
            </div>
          )}
          {isReplay && layers.perimeter && (
            <div className={styles.legendRow}>
              <Swatch color="var(--incident-high)" opacity={0.18} />
              Периметр
            </div>
          )}
          {layers.incidents && (
            <div className={styles.legendRow}>
              <FlameGlyph tone="confirmed" />
              Пиксели при приближении
            </div>
          )}
        </div>
      ) : (
        <div className={styles.legendRows}>
          <div className={styles.legendRow}>
            <FlameGlyph tone="watch" />
            Свежие, до 6 ч
          </div>
          <div className={styles.legendRow}>
            <FlameGlyph tone="confirmed" />
            Более ранние
          </div>
          <div className={styles.legendRow}>
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
              <circle
                cx="11"
                cy="11"
                r="9"
                fill="var(--observation)"
                fillOpacity="0.14"
                stroke="var(--observation)"
                strokeOpacity="0.65"
              />
            </svg>
            Кластер детекций
          </div>
        </div>
      )}
      {isReplay &&
        selected &&
        (layers.forecastP50 || layers.forecastP80 || layers.forecastP95) && (
          <>
            <h3 className={styles.legendTitle}>Прогноз · 24 ч</h3>
            <div className={styles.legendRows}>
              {layers.forecastP50 && (
                <div className={styles.legendRow}>
                  <Swatch color="var(--forecast-50)" opacity={0.35} />
                  P50 — наиболее вероятно
                </div>
              )}
              {layers.forecastP80 && (
                <div className={styles.legendRow}>
                  <Swatch color="var(--forecast-80)" opacity={0.22} />
                  P80
                </div>
              )}
              {layers.forecastP95 && (
                <div className={styles.legendRow}>
                  <Swatch color="var(--forecast-95)" opacity={0.12} dashed />
                  P95 — неопределённость
                </div>
              )}
            </div>
          </>
        )}
      {layers.monitoringAoi && (
        <>
          <h3 className={styles.legendTitle}>Территория</h3>
          <div className={styles.legendRows}>
            <div className={styles.legendRow}>
              <Swatch color="var(--protected-area)" opacity={0.2} />
              АОИ · Нижнее Поволжье и Подонье
            </div>
          </div>
        </>
      )}
      {layers.monitoringChips && (
        <>
          <h3 className={styles.legendTitle}>Датасет</h3>
          <div className={styles.legendRows}>
            <div className={styles.legendRow}>
              <Swatch color="var(--burn-scar)" opacity={0.35} />
              Чипы train · BS / AF
            </div>
          </div>
        </>
      )}
      {isReplay &&
        (layers.burnScars ||
          layers.thermalMemory ||
          layers.infrastructure ||
          layers.wind ||
          layers.clouds) && <h3 className={styles.legendTitle}>Контекст</h3>}
      {isReplay && (
        <div className={styles.legendRows}>
          {layers.burnScars && (
            <div className={styles.legendRow}>
              <Swatch color="var(--burn-scar)" opacity={0.35} />
              Гарь
            </div>
          )}
          {layers.wind && (
            <div className={styles.legendRow}>
              <ArrowGlyph />
              Ветер · куда дует · м/с
            </div>
          )}
          {layers.clouds && (
            <div className={styles.legendRow}>
              <Swatch color="var(--cloud)" opacity={0.3} dashed />
              Облачность
            </div>
          )}
          {layers.thermalMemory && (
            <div className={styles.legendRow}>
              <svg
                width="22"
                height="14"
                viewBox="0 0 22 14"
                aria-hidden="true"
              >
                <path
                  d="M11 1.5 L16.5 7 L11 12.5 L5.5 7 Z"
                  fill="none"
                  stroke="var(--thermal-source)"
                  strokeWidth="1.4"
                />
              </svg>
              Постоянный тепловой источник
            </div>
          )}
          {layers.infrastructure && (
            <div className={styles.legendRow}>
              <Swatch color="var(--infrastructure)" line dashed />
              ЛЭП / инфраструктура
            </div>
          )}
        </div>
      )}
    </section>
  );
}
