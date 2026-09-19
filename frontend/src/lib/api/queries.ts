"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, type IncidentQuery } from "./endpoints";
import type { BBox, TrainChipKind } from "./types";

const MINUTE = 60_000;

export const queryKeys = {
  overview: ["overview"] as const,
  incidents: (query: IncidentQuery) => ["incidents", query] as const,
  incident: (id: string) => ["incident", id] as const,
  incidentObservations: (id: string) => ["incident", id, "observations"] as const,
  incidentTimeline: (id: string) => ["incident", id, "timeline"] as const,
  incidentForecast: (id: string) => ["incident", id, "forecast"] as const,
  timeline: (from: string, to: string) => ["timeline", from, to] as const,
  histogram: (from: string, to: string, bins: number) => ["histogram", from, to, bins] as const,
  burnScars: (region?: string | null) => ["burn-scars", region ?? "all"] as const,
  burnScar: (id: string) => ["burn-scar", id] as const,
  analytics: (params: { from?: string; to?: string; region?: string | null }) => ["analytics", params] as const,
  hotspots: (bbox: BBox | null, aggregated: boolean, from?: string) => ["map", "hotspots", bbox, aggregated, from] as const,
  layer: (name: string, bbox?: BBox | null) => ["map", name, bbox ?? null] as const,
  liveStatus: ["live", "status"] as const,
  liveHotspots: (bbox: BBox | null) => ["live", "hotspots", bbox] as const,
  liveIncidents: (bbox: BBox | null) => ["live", "incidents", bbox] as const,
  analysisDatasets: ["analysis", "datasets"] as const,
  trainChips: (params: { kind?: TrainChipKind; has_fire?: boolean; q?: string }) =>
    ["datasets", "train", params] as const,
  trainChip: (id: string) => ["datasets", "train", "chip", id] as const,
  mlStatus: ["ml", "status"] as const,
};

export function useAnalysisDatasets() {
  return useQuery({
    queryKey: queryKeys.analysisDatasets,
    queryFn: ({ signal }) => api.analysis.datasets(signal),
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export function useTrainChips(params: { kind?: TrainChipKind; has_fire?: boolean; q?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: queryKeys.trainChips(params),
    queryFn: ({ signal }) => api.datasets.train({ ...params, limit: params.limit ?? 200 }, signal),
    staleTime: 5 * MINUTE,
    placeholderData: keepPreviousData,
  });
}

export function useTrainChip(chipId: string | null) {
  return useQuery({
    queryKey: queryKeys.trainChip(chipId ?? ""),
    queryFn: ({ signal }) => api.datasets.chip(chipId as string, signal),
    enabled: Boolean(chipId),
  });
}

export function useMlStatus() {
  return useQuery({
    queryKey: queryKeys.mlStatus,
    queryFn: ({ signal }) => api.ml.status(signal),
    staleTime: MINUTE,
  });
}

const LIVE_POLL_MS = Number(process.env.NEXT_PUBLIC_LIVE_POLL_SECONDS ?? 60) * 1000;

export function useLiveStatus() {
  return useQuery({
    queryKey: queryKeys.liveStatus,
    queryFn: ({ signal }) => api.live.status(signal),
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useLiveHotspots(bbox: BBox | null, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.liveHotspots(bbox),
    queryFn: ({ signal }) => api.live.hotspots(bbox, signal),
    enabled: enabled && bbox !== null,
    placeholderData: keepPreviousData,
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useLiveIncidents(bbox: BBox | null, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.liveIncidents(bbox),
    queryFn: ({ signal }) => api.live.incidents(bbox, signal),
    enabled: enabled && bbox !== null,
    placeholderData: keepPreviousData,
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useOverview() {
  return useQuery({
    queryKey: queryKeys.overview,
    queryFn: ({ signal }) => api.overview(signal),
    refetchInterval: MINUTE,
  });
}

export function useIncidents(query: IncidentQuery = {}) {
  return useQuery({
    queryKey: queryKeys.incidents(query),
    queryFn: ({ signal }) => api.incidents(query, signal),
    refetchInterval: MINUTE,
    placeholderData: keepPreviousData,
  });
}

export function useIncident(id: string | null) {
  return useQuery({
    queryKey: queryKeys.incident(id ?? ""),
    queryFn: ({ signal }) => api.incident(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: MINUTE,
  });
}

export function useIncidentObservations(id: string | null) {
  return useQuery({
    queryKey: queryKeys.incidentObservations(id ?? ""),
    queryFn: ({ signal }) => api.incidentObservations(id as string, signal),
    enabled: Boolean(id),
  });
}

export function useIncidentTimeline(id: string | null) {
  return useQuery({
    queryKey: queryKeys.incidentTimeline(id ?? ""),
    queryFn: ({ signal }) => api.incidentTimeline(id as string, signal),
    enabled: Boolean(id),
  });
}

export function useIncidentForecast(id: string | null) {
  return useQuery({
    queryKey: queryKeys.incidentForecast(id ?? ""),
    queryFn: ({ signal }) => api.incidentForecast(id as string, signal),
    enabled: Boolean(id),
  });
}

export function useTimelineEvents(from: string, to: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.timeline(from, to),
    queryFn: ({ signal }) => api.timeline(from, to, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useBurnScars(region?: string | null) {
  return useQuery({
    queryKey: queryKeys.burnScars(region),
    queryFn: ({ signal }) => api.burnScars(region, signal),
  });
}

export function useBurnScar(id: string | null) {
  return useQuery({
    queryKey: queryKeys.burnScar(id ?? ""),
    queryFn: ({ signal }) => api.burnScar(id as string, signal),
    enabled: Boolean(id),
  });
}

export function useAnalytics(params: { from?: string; to?: string; region?: string | null }) {
  return useQuery({
    queryKey: queryKeys.analytics(params),
    queryFn: ({ signal }) => api.analytics(params, signal),
    placeholderData: keepPreviousData,
  });
}

export function useHotspots(bbox: BBox | null, aggregated: boolean, from?: string) {
  return useQuery({
    queryKey: queryKeys.hotspots(bbox, aggregated, from),
    queryFn: ({ signal }) => api.map.hotspots({ bbox, zoom: aggregated ? 2 : undefined, from }, signal),
    enabled: bbox !== null,
    placeholderData: keepPreviousData,
    refetchInterval: 5 * MINUTE,
  });
}

export function useMapLayer<T>(name: string, bbox: BBox | null, fetcher: (bbox: BBox | null, signal?: AbortSignal) => Promise<T>, enabled = true) {
  return useQuery({
    queryKey: queryKeys.layer(name, bbox),
    queryFn: ({ signal }) => fetcher(bbox, signal),
    enabled: enabled && bbox !== null,
    placeholderData: keepPreviousData,
    staleTime: 5 * MINUTE,
  });
}

export function useObservationHistogram(from: string, to: string, bins: number, enabled = true) {
  return useQuery({
    queryKey: queryKeys.histogram(from, to, bins),
    queryFn: ({ signal }) => api.histogram({ from, to, bins }, signal),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: 5 * MINUTE,
  });
}
