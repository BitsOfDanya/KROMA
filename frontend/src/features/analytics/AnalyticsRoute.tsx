"use client";

import { useSearchParams } from "next/navigation";

import { AnalysisPage } from "@/features/analysis/AnalysisPage";

import { AnalyticsView } from "./AnalyticsView";

export function AnalyticsRoute() {
  const searchParams = useSearchParams();
  return searchParams.get("tab") === "area" ? <AnalysisPage /> : <AnalyticsView />;
}
