"use client";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useWorkspace, type AppMode } from "@/state/workspace";

export function ModeSwitch() {
  const appMode = useWorkspace((state) => state.appMode);
  const setAppMode = useWorkspace((state) => state.setAppMode);

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
