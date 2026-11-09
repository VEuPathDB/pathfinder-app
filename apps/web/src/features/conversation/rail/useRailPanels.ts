import type { Strategy } from "@pathfinder/shared";
import { FlaskConical, ListChecks, Workflow, type LucideIcon } from "lucide-react";

import { useEdaStore } from "@/state/eda";
import {
  lastSeenFor,
  useRightRailStore,
  type RightRailPanel,
} from "@/state/useRightRailStore";

import { useChatHelpers } from "../runtime/chatHelpersContext";
import { computeRailActivity } from "./railActivity";

export interface RailPanelButton {
  id: RightRailPanel;
  icon: LucideIcon;
  label: string;
  open: boolean;
  hasUpdate: boolean;
  toggle: () => void;
}

const PANELS: { id: RightRailPanel; icon: LucideIcon; label: string }[] = [
  { id: "strategy", icon: Workflow, label: "Strategy" },
  { id: "review", icon: ListChecks, label: "Review" },
  { id: "study", icon: FlaskConical, label: "Study" },
];

export function useRailPanels(
  conversationId: string,
  strategy: Strategy | null,
): RailPanelButton[] {
  const openPanel = useRightRailStore((s) => s.openPanel);
  const lastSeen = lastSeenFor(
    useRightRailStore((s) => s.lastSeen),
    conversationId,
  );
  const togglePanel = useRightRailStore((s) => s.togglePanel);
  const studyOpen = useEdaStore((s) => s.analysis) !== null;
  const activity = computeRailActivity(useChatHelpers().messages);
  const strategyStepCount = strategy?.steps.length ?? 0;
  const counts: Record<RightRailPanel, [seen: number, now: number]> = {
    strategy: [lastSeen.strategyStepCount, strategyStepCount],
    review: [lastSeen.reviewCount, activity.reviewCount],
    study: [lastSeen.studyCount, activity.studyCount],
  };
  const markers: Record<RightRailPanel, Partial<typeof lastSeen>> = {
    strategy: { strategyStepCount },
    review: { reviewCount: activity.reviewCount },
    study: { studyCount: activity.studyCount },
  };
  return PANELS.filter(
    ({ id }) =>
      id !== "study" || studyOpen || activity.studyCount > 0 || openPanel === "study",
  ).map(({ id, icon, label }) => ({
    id,
    icon,
    label,
    open: openPanel === id,
    hasUpdate: counts[id][0] !== counts[id][1],
    toggle: () => togglePanel(conversationId, id, markers[id]),
  }));
}
