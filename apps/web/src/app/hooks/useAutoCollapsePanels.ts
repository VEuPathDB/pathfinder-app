import { useState } from "react";
import { useEventListener } from "usehooks-ts";

import { viewportIsNarrow } from "@/lib/layout/viewport";
import { useLeftSidebarStore, useRightRailStore } from "@/state/useRightRailStore";

export function useAutoCollapsePanels(): void {
  const setCollapsed = useLeftSidebarStore((s) => s.setCollapsed);
  const closePanel = useRightRailStore((s) => s.closePanel);
  const [checkedOnMount, setCheckedOnMount] = useState(false);

  function collapseWhenNarrow(): void {
    if (viewportIsNarrow()) {
      setCollapsed(true);
      closePanel();
    }
  }

  if (!checkedOnMount && typeof window !== "undefined") {
    setCheckedOnMount(true);
    collapseWhenNarrow();
  }

  useEventListener("resize", collapseWhenNarrow);
}
