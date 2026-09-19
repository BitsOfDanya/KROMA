"use client";

import dynamic from "next/dynamic";

const PredictView = dynamic(() => import("@/features/predict/PredictView").then((mod) => mod.PredictView), {
  ssr: false,
});

export default function PredictPage() {
  return <PredictView />;
}
