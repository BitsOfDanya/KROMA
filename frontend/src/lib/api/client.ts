export class ApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(message: string, status: number, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export type QueryValue = string | number | boolean | null | undefined | readonly (string | number)[];

export function buildQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length === 0) continue;
      search.set(key, value.join(","));
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function errorDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
      .filter(Boolean)
      .join("; ") || fallback;
  }
  return fallback;
}

export async function apiGet<T>(path: string, params: Record<string, QueryValue> = {}, signal?: AbortSignal): Promise<T> {
  const url = `${API_BASE}${path}${buildQuery(params)}`;
  let response: Response;
  try {
    response = await fetch(url, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("API недоступен", 0, path);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = errorDetail(await response.json(), detail);
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(detail || `HTTP ${response.status}`, response.status, path);
  }
  return (await response.json()) as T;
}

export interface DownloadedFile {
  blob: Blob;
  filename: string;
}

export async function apiDownload(
  path: string,
  params: Record<string, QueryValue>,
  signal?: AbortSignal,
): Promise<DownloadedFile> {
  const url = `${API_BASE}${path}${buildQuery(params)}`;
  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("API недоступен", 0, path);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = errorDetail(await response.json(), detail);
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(detail || `HTTP ${response.status}`, response.status, path);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  return { blob: await response.blob(), filename: match?.[1] ?? "kroma-export" };
}
