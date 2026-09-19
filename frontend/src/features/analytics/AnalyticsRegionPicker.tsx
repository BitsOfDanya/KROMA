"use client";

import { Check, ChevronDown, MapPin } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { useDismiss } from "@/components/ui/useDismiss";
import type { Region } from "@/lib/api/types";

import styles from "./analytics.module.css";

interface AnalyticsRegionPickerProps {
  regions: Region[];
  value: string | null;
  onChange: (value: string | null) => void;
}

export function AnalyticsRegionPicker({ regions, value, onChange }: AnalyticsRegionPickerProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(rootRef, open, close);

  const selected = regions.find((region) => region.id === value);
  const choices = [{ id: "", name: "Все регионы", short_name: "Общая сводка" }, ...regions];

  return (
    <div className={styles.regionPicker} ref={rootRef}>
      <button
        type="button"
        className={styles.regionTrigger}
        aria-label="Регион"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <MapPin size={16} aria-hidden="true" />
        <span>{selected?.short_name ?? "Все регионы"}</span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      {open && (
        <div className={styles.regionMenu} role="listbox" aria-label="Выбор региона">
          <div className={styles.regionMenuHeading}>Территория сводки</div>
          {choices.map((region) => {
            const active = (region.id || null) === value;
            const scenario = region.name.includes("(сценарий)");
            return (
              <button
                key={region.id || "all"}
                type="button"
                role="option"
                aria-selected={active}
                className={styles.regionOption}
                onClick={() => {
                  onChange(region.id || null);
                  setOpen(false);
                }}
              >
                <span className={styles.regionOptionIcon}><MapPin size={16} aria-hidden="true" /></span>
                <span className={styles.regionOptionText}>
                  <strong>{region.name}</strong>
                  <small>{region.id ? (scenario ? "Сценарный регион" : "Регион в сводке") : "Все доступные территории"}</small>
                </span>
                {active && <Check size={16} className={styles.regionOptionCheck} aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
