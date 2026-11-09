import { useRef, useState } from "react";
import { useEventListener } from "usehooks-ts";

import {
  MIN_CHAT_WIDTH_PX,
  NAV_RAIL_WIDTH_PX,
  RIGHT_PANEL_WIDTH_PX,
  SIDEBAR_SEPARATOR_PX,
  SIDEBAR_WIDTH_PX,
} from "@/lib/layout/dock";
import { useLeftSidebarStore, useRightRailStore } from "@/state/useRightRailStore";

const MIN_SIDEBAR_PX = 220;

export function useSidebarResize() {
  const sidebarWidth = useLeftSidebarStore((s) => s.width);
  const setSidebarWidth = useLeftSidebarStore((s) => s.setWidth);
  const [dragging, setDragging] = useState(false);
  const layoutRef = useRef<HTMLDivElement>(null);

  const handleMove = (event: MouseEvent) => {
    if (!dragging) return;
    const container = layoutRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const rightOpen = useRightRailStore.getState().openPanel !== null;
    const room =
      rect.width -
      NAV_RAIL_WIDTH_PX -
      SIDEBAR_SEPARATOR_PX -
      (rightOpen ? RIGHT_PANEL_WIDTH_PX : 0) -
      MIN_CHAT_WIDTH_PX;
    const widest = Math.max(MIN_SIDEBAR_PX, Math.min(SIDEBAR_WIDTH_PX, room));
    setSidebarWidth(
      Math.min(Math.max(event.clientX - rect.left, MIN_SIDEBAR_PX), widest),
    );
  };

  const handleUp = () => setDragging(false);

  useEventListener("mousemove", handleMove);
  useEventListener("mouseup", handleUp);

  return {
    layoutRef,
    sidebarWidth,
    isDragging: dragging,
    startDragging: () => setDragging(true),
  };
}
