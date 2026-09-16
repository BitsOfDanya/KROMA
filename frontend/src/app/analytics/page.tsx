"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const AnalyticsView = dynamic(() => import("@/features/analytics/AnalyticsView").then((mod) => mod.AnalyticsView), {
  ssr: false,
});

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <AnalyticsView />
    </Suspense>
  );
}
