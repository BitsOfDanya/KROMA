"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const AnalyticsRoute = dynamic(() => import("@/features/analytics/AnalyticsRoute").then((mod) => mod.AnalyticsRoute), {
  ssr: false,
});

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <AnalyticsRoute />
    </Suspense>
  );
}
