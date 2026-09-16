import type { PaddingOptions } from "maplibre-gl";

import { useWorkspace } from "@/state/workspace";

export function cameraPadding(container: HTMLElement): PaddingOptions {
  const state = useWorkspace.getState();
  const width = container.clientWidth;
  const compact = width < 1100;
  const left = state.panel && !compact ? 460 : 80;
  const right = state.selectedIncidentId && !compact ? 460 : 60;
  const bottom = state.timelineExpanded ? 190 : 110;
  const horizontal = Math.max(0, width - left - right);
  if (horizontal < 240) return { top: 60, bottom, left: 40, right: 40 };
  return { top: 70, bottom, left, right };
}
