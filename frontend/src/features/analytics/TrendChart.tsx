"use client";

import { useMemo, useState } from "react";

import type { AnalyticsSummary } from "@/lib/api/types";
import { formatArea, formatDate, formatInteger } from "@/lib/format";

const WIDTH = 640;
const HEIGHT = 220;
const PAD_LEFT = 44;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 26;

export function TrendChart({ series }: { series: AnalyticsSummary["series"] }) {
  const [hover, setHover] = useState<number | null>(null);

  const { points, maxArea } = useMemo(() => {
    const maxArea = Math.max(1, ...series.map((point) => point.burned_area_ha));
    const maxIncidents = Math.max(1, ...series.map((point) => point.incidents));
    const innerWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
    const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
    const step = series.length > 1 ? innerWidth / (series.length - 1) : 0;
    const points = series.map((point, index) => ({
      x: PAD_LEFT + step * index,
      y: PAD_TOP + innerHeight - (point.burned_area_ha / maxArea) * innerHeight,
      barHeight: (point.incidents / maxIncidents) * (innerHeight * 0.28),
      point,
    }));
    return { points, maxArea };
  }, [series]);

  if (series.length === 0) {
    return <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-tertiary)", fontSize: 12.5 }}>Нет данных за период</div>;
  }

  const path = points.map((item, index) => `${index === 0 ? "M" : "L"}${item.x} ${item.y}`).join(" ");
  const areaPath = `${path} L${points.at(-1)!.x} ${HEIGHT - PAD_BOTTOM} L${points[0].x} ${HEIGHT - PAD_BOTTOM} Z`;
  const innerHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const active = hover !== null ? points[hover] : null;

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Динамика площади гарей и числа событий по неделям" style={{ width: "100%", height: "auto" }}>
      {[0, 0.5, 1].map((ratio) => (
        <line
          key={ratio}
          x1={PAD_LEFT}
          x2={WIDTH - PAD_RIGHT}
          y1={PAD_TOP + innerHeight * (1 - ratio)}
          y2={PAD_TOP + innerHeight * (1 - ratio)}
          stroke="var(--border)"
        />
      ))}
      <text x={4} y={PAD_TOP + 4} fontSize="10" fill="var(--text-tertiary)">{formatArea(maxArea)}</text>
      <text x={4} y={HEIGHT - PAD_BOTTOM + 4} fontSize="10" fill="var(--text-tertiary)">0</text>
      {points.map((item) => (
        <rect
          key={`bar-${item.point.week_start}`}
          x={item.x - 3}
          y={HEIGHT - PAD_BOTTOM - item.barHeight}
          width={6}
          height={item.barHeight}
          rx={1.5}
          fill="var(--observation)"
          opacity={0.35}
        />
      ))}
      <path d={areaPath} fill="var(--burn-scar)" opacity={0.12} />
      <path d={path} fill="none" stroke="var(--burn-scar)" strokeWidth={1.6} />
      {points.map((item, index) => (
        <g key={item.point.week_start}>
          <circle cx={item.x} cy={item.y} r={active === item ? 3.5 : 2.2} fill="var(--burn-scar)" />
          <rect
            x={item.x - (points.length > 1 ? (points[1].x - points[0].x) / 2 : 20)}
            y={PAD_TOP}
            width={points.length > 1 ? points[1].x - points[0].x : 40}
            height={innerHeight}
            fill="transparent"
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover((current) => (current === index ? null : current))}
          />
          {index % Math.ceil(points.length / 8 || 1) === 0 && (
            <text x={item.x} y={HEIGHT - 8} fontSize="10" textAnchor="middle" fill="var(--text-tertiary)">
              {formatDate(item.point.week_start)}
            </text>
          )}
        </g>
      ))}
      {active && (
        <g transform={`translate(${Math.min(active.x + 8, WIDTH - 150)}, ${PAD_TOP + 4})`}>
          <rect width={140} height={44} rx={6} fill="var(--surface-elevated)" stroke="var(--border-strong)" />
          <text x={8} y={16} fontSize="10.5" fill="var(--text-tertiary)">{formatDate(active.point.week_start)}</text>
          <text x={8} y={30} fontSize="11" fill="var(--text)">{formatArea(active.point.burned_area_ha)} · {formatInteger(active.point.incidents)} событ.</text>
        </g>
      )}
    </svg>
  );
}
