"use client";

import { useEffect, useRef, useState } from "react";

export function AnimatedNumber({ value, duration = 450 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(value);
  const current = useRef(value);

  useEffect(() => {
    const from = current.current;
    if (from === value) return;
    const start = performance.now();
    let frame = 0;
    const step = (time: number) => {
      const progress = Math.min(1, (time - start) / duration);
      const eased = 1 - (1 - progress) ** 3;
      const next = Math.round(from + (value - from) * eased);
      current.current = next;
      setDisplay(next);
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  return <>{display}</>;
}
