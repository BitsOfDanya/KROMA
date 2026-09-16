"use client";

import { useMemo } from "react";

import { useIncidents } from "@/lib/api/queries";
import type { IncidentSummary } from "@/lib/api/types";
import { useWorkspace } from "@/state/workspace";

export function useFilteredIncidents() {
  const query = useIncidents();
  const regionId = useWorkspace((state) => state.regionId);
  const statusFilter = useWorkspace((state) => state.statusFilter);
  const priorityMin = useWorkspace((state) => state.priorityMin);

  const items = useMemo<IncidentSummary[]>(() => {
    const source = query.data?.items ?? [];
    return source.filter(
      (item) =>
        (!regionId || item.region_id === regionId) &&
        (statusFilter.length === 0 || statusFilter.includes(item.status)) &&
        item.priority >= priorityMin,
    );
  }, [query.data, regionId, statusFilter, priorityMin]);

  return { ...query, items };
}
