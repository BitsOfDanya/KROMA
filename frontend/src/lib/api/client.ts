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
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(detail || `HTTP ${response.status}`, response.status, path);
  }
  return (await response.json()) as T;
}
