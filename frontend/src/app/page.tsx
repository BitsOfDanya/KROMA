"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const OverviewMapView = dynamic(() => import("@/features/overview/OverviewMapView").then((mod) => mod.OverviewMapView), {
  ssr: false,
});

export default function OverviewPage() {
  return (
    <Suspense fallback={null}>
      <OverviewMapView />
    </Suspense>
  );
}
