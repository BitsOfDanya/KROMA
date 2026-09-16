const LOCALE = "ru-RU";

const integer = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1, minimumFractionDigits: 1 });

export function formatInteger(value: number): string {
  return integer.format(Math.round(value));
}

export function formatArea(hectares: number): string {
  if (!Number.isFinite(hectares)) return "—";
  if (hectares >= 10_000) {
    const km2 = hectares / 100;
    return `${formatInteger(km2)} км²`;
  }
  if (hectares < 10) return `${oneDecimal.format(hectares)} га`;
  return `${formatInteger(hectares)} га`;
}

export function formatDistance(km: number): string {
  if (!Number.isFinite(km)) return "—";
  if (km < 1) return `${formatInteger(Math.max(0, km * 1000))} м`;
  if (km < 100) return `${oneDecimal.format(km)} км`;
  return `${formatInteger(km)} км`;
}

export function formatCoordinate([lon, lat]: [number, number]): string {
  const latLabel = `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? "с. ш." : "ю. ш."}`;
  const lonLabel = `${Math.abs(lon).toFixed(3)}° ${lon >= 0 ? "в. д." : "з. д."}`;
  return `${latLabel}, ${lonLabel}`;
}

function plural(value: number, forms: [string, string, string]): string {
  const mod10 = value % 10;
  const mod100 = value % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1];
  return forms[2];
}

export function pluralize(value: number, forms: [string, string, string]): string {
  return `${formatInteger(value)} ${plural(Math.abs(Math.round(value)), forms)}`;
}

export function formatRelative(iso: string | number | Date, now: number = Date.now()): string {
  const time = new Date(iso).getTime();
  const diff = time - now;
  const minutes = Math.round(Math.abs(diff) / 60_000);
  const future = diff > 0;
  let label: string;
  if (minutes < 1) return future ? "менее минуты" : "только что";
  if (minutes < 60) label = `${minutes} мин`;
  else if (minutes < 60 * 24) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    label = hours < 6 && rest >= 5 ? `${hours} ч ${rest} мин` : `${Math.round(minutes / 60)} ч`;
  } else {
    const days = Math.round(minutes / (60 * 24));
    label = `${days} д`;
  }
  return future ? `через ${label}` : `${label} назад`;
}

const timeFormat = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit" });
const dateFormat = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short" });
const dateLongFormat = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const exactFormat = new Intl.DateTimeFormat(LOCALE, {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
});

export const formatTime = (value: string | number | Date) => timeFormat.format(new Date(value));
export const formatDate = (value: string | number | Date) => dateFormat.format(new Date(value)).replace(".", "");
export const formatDateLong = (value: string | number | Date) => dateLongFormat.format(new Date(value));
export const formatDateTime = (value: string | number | Date) => dateTimeFormat.format(new Date(value)).replace(".", "");
export const formatExact = (value: string | number | Date) => exactFormat.format(new Date(value));

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} мин`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest ? `${hours} ч ${rest} мин` : `${hours} ч`;
}

export function formatSpeed(metersPerHour: number): string {
  if (metersPerHour >= 1000) return `${oneDecimal.format(metersPerHour / 1000)} км/ч`;
  return `${formatInteger(metersPerHour)} м/ч`;
}

const COMPASS = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"];

export function compassPoint(degrees: number): string {
  const index = Math.round((((degrees % 360) + 360) % 360) / 45) % 8;
  return COMPASS[index];
}

export function formatPercent(share: number): string {
  return `${formatInteger(share * 100)}%`;
}
