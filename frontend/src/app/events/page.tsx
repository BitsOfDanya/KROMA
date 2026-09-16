"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const EventsView = dynamic(() => import("@/features/events/EventsView").then((mod) => mod.EventsView), { ssr: false });

export default function EventsPage() {
  return (
    <Suspense fallback={null}>
      <EventsView />
    </Suspense>
  );
}
