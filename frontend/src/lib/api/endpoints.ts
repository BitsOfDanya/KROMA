import { apiDownload, apiGet } from "./client";
import type {
  AnalysisDatasetCatalog,
  AnalysisQuery,
  AnalysisResult,
  AnalyticsSummary,
  BBox,
  BurnScar,
  BurnScarList,
  FeatureCollection,
  HotspotProperties,
  IncidentDetail,
  IncidentList,
  IncidentStatus,
  IncidentTimeline,
  LiveStatus,
  ObservationHistogram,
  Overview,
  RiskObjectKind,
  TimelineResponse,
} from "./types";

export interface IncidentQuery {
  status?: IncidentStatus[];
  priorityMin?: number;
  region?: string | null;
  from?: string;
  to?: string;
  bbox?: BBox;
  q?: string;
}

const bboxParam = (bbox?: BBox | null, precision = 3) =>
  bbox ? bbox.map((value) => (precision < 0 ? String(value) : value.toFixed(precision))).join(",") : undefined;

const analysisParams = (query: AnalysisQuery) => ({
  dataset_id: query.datasetId,
  dataset_version: query.datasetVersion,
  bbox: bboxParam(query.bbox, -1),
  from: query.from,
  to: query.to,
});

export const api = {
  overview: (signal?: AbortSignal) => apiGet<Overview>("/api/v1/overview", {}, signal),

  incidents: (query: IncidentQuery = {}, signal?: AbortSignal) =>
    apiGet<IncidentList>(
      "/api/v1/incidents",
      {
        status: query.status,
        priority_min: query.priorityMin,
        region: query.region,
        from: query.from,
        to: query.to,
        bbox: bboxParam(query.bbox),
        q: query.q,
      },
      signal,
    ),

  incident: (id: string, signal?: AbortSignal) =>
    apiGet<IncidentDetail>(`/api/v1/incidents/${encodeURIComponent(id)}`, {}, signal),

  incidentObservations: (id: string, signal?: AbortSignal) =>
    apiGet<FeatureCollection<HotspotProperties>>(`/api/v1/incidents/${encodeURIComponent(id)}/observations`, {}, signal),

  incidentTimeline: (id: string, signal?: AbortSignal) =>
    apiGet<IncidentTimeline>(`/api/v1/incidents/${encodeURIComponent(id)}/timeline`, {}, signal),

  incidentForecast: (id: string, signal?: AbortSignal) =>
    apiGet<FeatureCollection>(`/api/v1/incidents/${encodeURIComponent(id)}/forecast`, {}, signal),

  timeline: (from: string, to: string, signal?: AbortSignal) =>
    apiGet<TimelineResponse>("/api/v1/timeline", { from, to }, signal),

  histogram: (params: { from: string; to: string; bins: number; bbox?: BBox | null }, signal?: AbortSignal) =>
    apiGet<ObservationHistogram>(
      "/api/v1/observations/histogram",
      { from: params.from, to: params.to, bins: params.bins, bbox: bboxParam(params.bbox) },
      signal,
    ),

  burnScars: (region?: string | null, signal?: AbortSignal) =>
    apiGet<BurnScarList>("/api/v1/burn-scars", { region }, signal),

  burnScar: (id: string, signal?: AbortSignal) =>
    apiGet<BurnScar>(`/api/v1/burn-scars/${encodeURIComponent(id)}`, {}, signal),

  analytics: (params: { from?: string; to?: string; region?: string | null }, signal?: AbortSignal) =>
    apiGet<AnalyticsSummary>("/api/v1/analytics/summary", params, signal),

  analysis: {
    datasets: (signal?: AbortSignal) =>
      apiGet<AnalysisDatasetCatalog>("/api/v1/analysis/datasets", {}, signal),
    run: (query: AnalysisQuery, signal?: AbortSignal) =>
      apiGet<AnalysisResult>("/api/v1/analysis", analysisParams(query), signal),
    contours: (query: AnalysisQuery, resultId: string, signal?: AbortSignal) =>
      apiDownload(
        "/api/v1/analysis/export/contours",
        { ...analysisParams(query), expected_result_id: resultId },
        signal,
      ),
    report: (query: AnalysisQuery, resultId: string, format: "csv" | "json", signal?: AbortSignal) =>
      apiDownload(
        "/api/v1/analysis/export/report",
        { ...analysisParams(query), expected_result_id: resultId, format },
        signal,
      ),
  },

  live: {
    status: (signal?: AbortSignal) => apiGet<LiveStatus>("/api/v1/live/status", {}, signal),
    hotspots: (bbox: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection<HotspotProperties>>("/api/v1/live/hotspots", { bbox: bboxParam(bbox) }, signal),
    incidents: (bbox: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/live/incidents", { bbox: bboxParam(bbox) }, signal),
  },

  map: {
    hotspots: (params: { bbox?: BBox | null; zoom?: number; from?: string; to?: string }, signal?: AbortSignal) =>
      apiGet<FeatureCollection<HotspotProperties>>(
        "/api/v1/map/hotspots",
        { bbox: bboxParam(params.bbox), zoom: params.zoom, from: params.from, to: params.to },
        signal,
      ),
    perimeters: (bbox?: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/map/perimeters", { bbox: bboxParam(bbox) }, signal),
    burnScars: (bbox?: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/map/burn-scars", { bbox: bboxParam(bbox) }, signal),
    riskObjects: (bbox?: BBox | null, kinds?: RiskObjectKind[], signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/map/risk-objects", { bbox: bboxParam(bbox), kind: kinds }, signal),
    thermalSources: (bbox?: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/map/thermal-sources", { bbox: bboxParam(bbox) }, signal),
    wind: (bbox?: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/map/wind", { bbox: bboxParam(bbox) }, signal),
    clouds: (bbox?: BBox | null, signal?: AbortSignal) =>
      apiGet<FeatureCollection>("/api/v1/map/clouds", { bbox: bboxParam(bbox) }, signal),
  },
};
