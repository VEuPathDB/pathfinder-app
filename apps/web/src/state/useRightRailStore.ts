import { z } from "zod";

import { SIDEBAR_WIDTH_PX, type Side } from "@/lib/layout/dock";

import { createPersistedStore, createStore } from "./middleware";

interface SideOrderState {
  lastOpened: Side | null;
  markOpened: (side: Side) => void;
}

export const useSideOrderStore = createStore<SideOrderState>(
  "SideOrderStore",
  (set) => ({
    lastOpened: null,
    markOpened: (side) => set({ lastOpened: side }),
  }),
);

const markOpened = (side: Side): void => useSideOrderStore.getState().markOpened(side);

export const RIGHT_RAIL_PANELS = ["strategy", "review", "study"] as const;

export type RightRailPanel = (typeof RIGHT_RAIL_PANELS)[number];

const SUCCESSORS: Record<string, RightRailPanel> = {
  strategy: "strategy",
  review: "review",
  study: "study",
  ledger: "review",
  tasks: "review",
  memories: "review",
  scratchpad: "review",
  eda: "study",
};

export function retiredPanel(id: unknown): RightRailPanel | null {
  return typeof id === "string" ? (SUCCESSORS[id] ?? null) : null;
}

interface LastSeen {
  strategyStepCount: number;
  reviewCount: number;
  studyCount: number;
}

const DEFAULT_LAST_SEEN: LastSeen = {
  strategyStepCount: 0,
  reviewCount: 0,
  studyCount: 0,
};

/** Markers for every conversation the rail has shown, keyed by conversation id. */
type LastSeenByConversation = Record<string, LastSeen>;

/** What the rail showed for one conversation, defaulting to a fresh thread. */
export function lastSeenFor(
  lastSeen: LastSeenByConversation,
  conversationId: string,
): LastSeen {
  return lastSeen[conversationId] ?? DEFAULT_LAST_SEEN;
}

const COUNT = z.number().catch(0);

const STORED = z.object({
  openPanel: z.unknown(),
  lastSeen: z
    .record(
      z.string(),
      z.object({
        strategyStepCount: COUNT,
        reviewCount: COUNT,
        studyCount: COUNT,
      }),
    )
    .catch({}),
  autoOpenedConversation: z.string().nullable().catch(null),
});

interface RightRailState {
  openPanel: RightRailPanel | null;
  lastSeen: LastSeenByConversation;
  autoOpenedConversation: string | null;

  openPanelId: (
    conversationId: string,
    panel: RightRailPanel,
    markers: Partial<LastSeen>,
  ) => void;
  togglePanel: (
    conversationId: string,
    panel: RightRailPanel,
    markers: Partial<LastSeen>,
  ) => void;
  closePanel: () => void;
  autoOpen: (conversationId: string, panel: RightRailPanel) => void;
}

function withMarkers(
  lastSeen: LastSeenByConversation,
  conversationId: string,
  markers: Partial<LastSeen>,
): LastSeenByConversation {
  return {
    ...lastSeen,
    [conversationId]: { ...lastSeenFor(lastSeen, conversationId), ...markers },
  };
}

export const useRightRailStore = createPersistedStore<RightRailState>(
  "RightRailStore",
  (set, get) => ({
    openPanel: null,
    lastSeen: {},
    autoOpenedConversation: null,

    openPanelId: (conversationId, panel, markers) => {
      markOpened("right");
      set((s) => ({
        openPanel: panel,
        lastSeen: withMarkers(s.lastSeen, conversationId, markers),
      }));
    },

    togglePanel: (conversationId, panel, markers) => {
      const current = get().openPanel;
      if (current === panel) {
        set({ openPanel: null });
        return;
      }
      markOpened("right");
      set((s) => ({
        openPanel: panel,
        lastSeen: withMarkers(s.lastSeen, conversationId, markers),
      }));
    },

    closePanel: () => set({ openPanel: null }),

    autoOpen: (conversationId, panel) => {
      if (get().autoOpenedConversation === conversationId) return;
      if (get().openPanel === null) markOpened("right");
      set((s) => ({
        autoOpenedConversation: conversationId,
        openPanel: s.openPanel ?? panel,
      }));
    },
  }),
  {
    name: "pathfinder-right-rail",
    partialize: (s) => ({
      openPanel: s.openPanel,
      lastSeen: s.lastSeen,
      autoOpenedConversation: s.autoOpenedConversation,
    }),
    merge: (stored, current) => {
      const parsed = STORED.safeParse(stored);
      if (!parsed.success) return current;
      return {
        ...current,
        openPanel: retiredPanel(parsed.data.openPanel),
        lastSeen: parsed.data.lastSeen,
        autoOpenedConversation: parsed.data.autoOpenedConversation,
      };
    },
  },
);

interface LeftSidebarState {
  collapsed: boolean;
  width: number;
  toggle: () => void;
  setCollapsed: (value: boolean) => void;
  setWidth: (width: number) => void;
}

export const useLeftSidebarStore = createPersistedStore<LeftSidebarState>(
  "LeftSidebarStore",
  (set, get) => ({
    collapsed: false,
    width: SIDEBAR_WIDTH_PX,
    toggle: () => {
      if (get().collapsed) markOpened("left");
      set((s) => ({ collapsed: !s.collapsed }));
    },
    setCollapsed: (value) => {
      if (!value) markOpened("left");
      set({ collapsed: value });
    },
    setWidth: (width) => set({ width }),
  }),
  {
    name: "pathfinder-left-sidebar",
    partialize: (s) => ({ collapsed: s.collapsed }),
  },
);
