import type { BurnSeverity, ForecastLevel, IncidentStatus, RiskObjectKind, Severity } from "./api/types";

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  suspected: "Предварительный",
  confirmed: "Подтверждён",
  monitoring: "Наблюдение",
  localized: "Локализован",
};

export const STATUS_TITLE: Record<IncidentStatus, string> = {
  suspected: "Предполагаемый пожар",
  confirmed: "Подтверждённый пожар",
  monitoring: "Пожар под наблюдением",
  localized: "Локализованный пожар",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Критический",
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};

export const BURN_SEVERITY_LABEL: Record<BurnSeverity, string> = {
  low: "Низкая",
  moderate: "Средняя",
  high: "Высокая",
};

export const RISK_KIND_LABEL: Record<RiskObjectKind, string> = {
  settlement: "Населённый пункт",
  power_line: "ЛЭП",
  road: "Дорога",
  infrastructure: "Инфраструктура",
  protected_area: "ООПТ",
};

export const FORECAST_LABEL: Record<ForecastLevel, string> = {
  p50: "P50",
  p80: "P80",
  p95: "P95",
};

export function severityForPriority(priority: number): Severity {
  if (priority >= 85) return "critical";
  if (priority >= 65) return "high";
  if (priority >= 40) return "medium";
  return "low";
}
