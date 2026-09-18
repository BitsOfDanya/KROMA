"use client";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useWorkspace, type AppMode } from "@/state/workspace";
import { usePathname, useSearchParams } from "next/navigation";

import styles from "./shell.module.css";

export function ModeSwitch() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const appMode = useWorkspace((state) => state.appMode);
  const setAppMode = useWorkspace((state) => state.setAppMode);

  if (pathname === "/analytics" && searchParams.get("tab") === "area") {
    return <span className={styles.preparedMode}>Подготовленный анализ</span>;
  }
  if (pathname !== "/") {
    return <span className={styles.preparedMode}>Демонстрационный сценарий</span>;
  }

  return (
    <SegmentedControl<AppMode>
      label="Режим карты"
      size="sm"
      value={appMode}
      onChange={setAppMode}
      options={[
        { value: "live", label: "Актуально", title: "Актуальные спутниковые данные NASA FIRMS" },
        { value: "replay", label: "Сценарий", title: "Фиксированный воспроизводимый сценарий" },
      ]}
    />
  );
}
