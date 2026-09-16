import { useState } from "react";
import { useEventListener } from "usehooks-ts";

import { viewportIsNarrow } from "@/lib/layout/viewport";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";

/** The width the gene-set panel takes when the window has room for it. */
export const WORKBENCH_SIDEBAR_WIDTH_PX = 384;

/**
 * Width that stays beside the gene-set panel in every window: the nav rail and
 * the gene-search edge tab.
 */
export const WORKBENCH_SIDE_CHROME_PX = 80;

/** The gene-set panel width that leaves the whole panel inside the viewport. */
export function workbenchSidebarWidth(viewportWidth: number): number {
  return Math.max(
    0,
    Math.min(WORKBENCH_SIDEBAR_WIDTH_PX, viewportWidth - WORKBENCH_SIDE_CHROME_PX),
  );
}

function measure(): number {
  if (typeof window === "undefined") return WORKBENCH_SIDEBAR_WIDTH_PX;
  return workbenchSidebarWidth(window.innerWidth);
}

/**
 * The width the workbench gene-set panel gets. A narrow window also closes both
 * workbench panels, so the routed content keeps the screen.
 */
export function useWorkbenchSidebarLayout(): number {
  const [width, setWidth] = useState(measure);
  const [checkedOnMount, setCheckedOnMount] = useState(false);

  function followViewport(): void {
    setWidth(measure());
    if (!viewportIsNarrow()) return;
    const panels = useWorkbenchStore.getState();
    if (panels.leftSidebarOpen) panels.toggleLeftSidebar();
    if (panels.geneSearchOpen) panels.toggleGeneSearch();
  }

  if (!checkedOnMount && typeof window !== "undefined") {
    setCheckedOnMount(true);
    followViewport();
  }

  useEventListener("resize", followViewport);

  return width;
}
