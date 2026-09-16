"use client";

import { Compass, Info, Minus, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useWorkspace, type BasemapMode } from "@/state/workspace";

import { MapLegend } from "./MapLegend";
import { useMapContext } from "./MapContext";
import styles from "./map.module.css";

const BASEMAPS: { value: BasemapMode; label: string }[] = [
  { value: "map", label: "Карта" },
  { value: "satellite", label: "Спутник" },
  { value: "terrain", label: "Рельеф" },
];

export function MapControls() {
  const { map } = useMapContext();
  const basemap = useWorkspace((state) => state.basemap);
  const setBasemap = useWorkspace((state) => state.setBasemap);
  const [legendOpen, setLegendOpen] = useState(true);
  const [bearing, setBearing] = useState(0);

  useEffect(() => {
    if (!map) return;
    const update = () => setBearing(map.getBearing());
    map.on("rotate", update);
    return () => {
      map.off("rotate", update);
    };
  }, [map]);

  return (
    <div className={styles.controls}>
      <SegmentedControl
        label="Подложка карты"
        value={basemap}
        options={BASEMAPS}
        onChange={setBasemap}
        className={styles.basemapSwitch}
      />
      <div className={styles.controlGroup}>
        <IconButton label="Приблизить" tooltipSide="left" icon={<Plus size={16} strokeWidth={1.75} />} onClick={() => map?.zoomIn()} />
        <IconButton label="Отдалить" tooltipSide="left" icon={<Minus size={16} strokeWidth={1.75} />} onClick={() => map?.zoomOut()} />
        <IconButton
          label="Север вверху"
          tooltipSide="left"
          icon={<Compass size={16} strokeWidth={1.75} style={{ transform: `rotate(${-bearing}deg)` }} />}
          onClick={() => map?.easeTo({ bearing: 0, pitch: 0 })}
        />
        <IconButton
          label={legendOpen ? "Скрыть легенду" : "Показать легенду"}
          tooltipSide="left"
          active={legendOpen}
          aria-expanded={legendOpen}
          icon={<Info size={16} strokeWidth={1.75} />}
          onClick={() => setLegendOpen((open) => !open)}
        />
      </div>
      {legendOpen && <MapLegend />}
    </div>
  );
}
