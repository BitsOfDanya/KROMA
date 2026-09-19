"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const ExplorerView = dynamic(() => import("@/features/explorer/ExplorerView").then((mod) => mod.ExplorerView), {
  ssr: false,
});

export default function ExplorerPage() {
  return (
    <Suspense fallback={null}>
      <ExplorerView />
    </Suspense>
  );
}
