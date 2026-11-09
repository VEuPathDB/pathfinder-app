import { useWindowSize } from "usehooks-ts";

import {
  dockLayout,
  RIGHT_PANEL_WIDTH_PX,
  type DockInput,
  type DockLayout,
} from "@/lib/layout/dock";

import {
  useLeftSidebarStore,
  useRightRailStore,
  useSideOrderStore,
} from "./useRightRailStore";

export function useDockLayout(): DockLayout {
  const { width: viewport } = useWindowSize({ initializeWithValue: false });
  const leftOpen = !useLeftSidebarStore((s) => s.collapsed);
  const leftWidth = useLeftSidebarStore((s) => s.width);
  const rightOpen = useRightRailStore((s) => s.openPanel) !== null;
  const lastOpened = useSideOrderStore((s) => s.lastOpened);
  if (viewport === undefined) return { leftFloats: false, rightFloats: false };
  return dockLayout({
    viewport,
    leftOpen,
    leftWidth,
    rightOpen,
    rightWidth: RIGHT_PANEL_WIDTH_PX,
    lastOpened,
  });
}

function storedInput(viewport: number): DockInput {
  const left = useLeftSidebarStore.getState();
  return {
    viewport,
    leftOpen: !left.collapsed,
    leftWidth: left.width,
    rightOpen: useRightRailStore.getState().openPanel !== null,
    rightWidth: RIGHT_PANEL_WIDTH_PX,
    lastOpened: useSideOrderStore.getState().lastOpened,
  };
}

export function dockLayoutAt(viewport: number): DockLayout {
  return dockLayout(storedInput(viewport));
}

export function currentDockLayout(): DockLayout {
  return dockLayoutAt(window.innerWidth);
}

export function rightWouldFloat(): boolean {
  return dockLayout({
    ...storedInput(window.innerWidth),
    rightOpen: true,
    lastOpened: "right",
  }).rightFloats;
}
