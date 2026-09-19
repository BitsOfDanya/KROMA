"use client";

import { Check, ChevronDown, MapPin } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { useDismiss } from "@/components/ui/useDismiss";
import { useOverview } from "@/lib/api/queries";
import { useWorkspace } from "@/state/workspace";

import styles from "./shell.module.css";

export function RegionSelect() {
  const overview = useOverview();
  const regionId = useWorkspace((state) => state.regionId);
  const setRegion = useWorkspace((state) => state.setRegion);
  const requestCamera = useWorkspace((state) => state.requestCamera);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);

  const regions = overview.data?.regions ?? [];
  const current = regions.find((region) => region.id === regionId);

  const choose = (id: string | null) => {
    setRegion(id);
    setOpen(false);
    const region = regions.find((item) => item.id === id);
    if (region) {
      requestCamera({ kind: "bounds", bbox: region.bbox, maxZoom: region.zoom + 1.2 });
    } else {
      requestCamera({ kind: "bounds", bbox: [38.3, 44.6, 48.0, 52.7], maxZoom: 5.4 });
    }
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        className={styles.regionButton}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <MapPin size={14} strokeWidth={1.75} />
        {current ? current.short_name : "Все регионы"}
        <ChevronDown size={13} strokeWidth={1.75} />
      </button>
      {open && (
        <div className={styles.menu} data-align="right" role="listbox" aria-label="Регион" style={{ width: 240 }}>
          {[{ id: null, name: "Все регионы" }, ...regions].map((region) => (
            <button
              key={region.id ?? "all"}
              type="button"
              role="option"
              aria-selected={region.id === regionId}
              className={styles.menuItem}
              onClick={() => choose(region.id)}
            >
              {region.name}
              {region.id === regionId && <Check size={14} className={styles.menuMeta} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
