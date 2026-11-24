import { createContext, useContext } from "react";
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

export const LeftSidebarDrawn = createContext(false);

export function useLeftSidebarDrawn(): boolean {
  return useContext(LeftSidebarDrawn);
}

export function useDockLayout(): DockLayout {
  const { width: viewport } = useWindowSize({ initializeWithValue: false });
  const leftDrawn = useLeftSidebarDrawn();
  const leftOpen = !useLeftSidebarStore((s) => s.collapsed);
  const leftWidth = useLeftSidebarStore((s) => s.width);
  const rightOpen = useRightRailStore((s) => s.openPanel) !== null;
  const lastOpened = useSideOrderStore((s) => s.lastOpened);
  if (viewport === undefined) return { leftFloats: false, rightFloats: false };
  return dockLayout({
    viewport,
    leftDrawn,
    leftOpen,
    leftWidth,
    rightOpen,
    rightWidth: RIGHT_PANEL_WIDTH_PX,
    lastOpened,
  });
}

function storedInput(viewport: number, leftDrawn: boolean): DockInput {
  const left = useLeftSidebarStore.getState();
  return {
    viewport,
    leftDrawn,
    leftOpen: !left.collapsed,
    leftWidth: left.width,
    rightOpen: useRightRailStore.getState().openPanel !== null,
    rightWidth: RIGHT_PANEL_WIDTH_PX,
    lastOpened: useSideOrderStore.getState().lastOpened,
  };
}

export function dockLayoutAt(viewport: number, leftDrawn: boolean): DockLayout {
  return dockLayout(storedInput(viewport, leftDrawn));
}

export function currentDockLayout(leftDrawn: boolean): DockLayout {
  return dockLayoutAt(window.innerWidth, leftDrawn);
}

export function railMayOpenItself(leftDrawn: boolean): boolean {
  if (typeof window === "undefined") return false;
  return !dockLayout({
    ...storedInput(window.innerWidth, leftDrawn),
    rightOpen: true,
    lastOpened: "right",
  }).rightFloats;
}
