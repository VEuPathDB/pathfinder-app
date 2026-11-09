import { useRef, useState } from "react";
import { useEventListener } from "usehooks-ts";

import { currentDockLayout, dockLayoutAt } from "@/state/useDockLayout";
import { useLeftSidebarStore, useRightRailStore } from "@/state/useRightRailStore";

export function useAutoCollapsePanels(pathname: string): void {
  const setCollapsed = useLeftSidebarStore((s) => s.setCollapsed);
  const closePanel = useRightRailStore((s) => s.closePanel);
  const [checkedOnMount, setCheckedOnMount] = useState(false);
  const [seenPath, setSeenPath] = useState(pathname);
  const [mountWidth] = useState(() =>
    typeof window === "undefined" ? null : window.innerWidth,
  );
  const lastWidth = useRef<number | null>(mountWidth);

  function closeFloatingPanels(): void {
    const { leftFloats, rightFloats } = currentDockLayout();
    if (leftFloats) setCollapsed(true);
    if (rightFloats) closePanel();
  }

  function closeNewlyFloatingPanels(): void {
    const before = lastWidth.current;
    const width = window.innerWidth;
    lastWidth.current = width;
    if (before === null || before === width) return;
    const was = dockLayoutAt(before);
    const now = dockLayoutAt(width);
    if (now.leftFloats && !was.leftFloats) setCollapsed(true);
    if (now.rightFloats && !was.rightFloats) closePanel();
  }

  if (seenPath !== pathname) {
    setSeenPath(pathname);
    queueMicrotask(closeFloatingPanels);
  }

  if (!checkedOnMount && typeof window !== "undefined") {
    setCheckedOnMount(true);
    closeFloatingPanels();
  }

  useEventListener("resize", closeNewlyFloatingPanels);
}
