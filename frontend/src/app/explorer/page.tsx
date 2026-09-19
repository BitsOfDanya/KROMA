"use client";

import dynamic from "next/dynamic";

const ExplorerView = dynamic(() => import("@/features/explorer/ExplorerView").then((mod) => mod.ExplorerView), {
  ssr: false,
});

export default function ExplorerPage() {
  return <ExplorerView />;
}
