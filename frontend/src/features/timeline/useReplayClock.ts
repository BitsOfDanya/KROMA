"use client";

import { useEffect } from "react";

import { advanceCursor } from "@/lib/replay";
import { useWorkspace } from "@/state/workspace";

export function useReplayClock() {
  const playing = useWorkspace((state) => state.playing);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let previous = performance.now();
    let accumulated = 0;
    const step = (time: number) => {
      const elapsed = Math.min(100, time - previous);
      previous = time;
      accumulated += elapsed;
      if (accumulated >= 50) {
        const state = useWorkspace.getState();
        const { cursor, finished } = advanceCursor(state.cursor, state.timeWindow, state.speed, accumulated, Date.now());
        accumulated = 0;
        state.setCursor(cursor);
        if (finished) {
          state.setPlaying(false);
          return;
        }
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing]);
}
