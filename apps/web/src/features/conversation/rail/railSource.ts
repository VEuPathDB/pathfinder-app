import type { Strategy } from "@strategist/shared";
import type { TaskListItem } from "@strategist/shared/generated/types/TaskListItem";
import type { ReactNode } from "react";

import type { EdaAnalysisSnapshot } from "@/state/eda";

export interface StrategyActions {
  openEditor: () => void;
  openStep: (stepId: string) => void;
  refresh: { run: () => void; pending: boolean };
  saveStep: (stepId: string) => void;
  insertSavedAt: (stepId: string) => void;
  insertSavedAsRoot: () => void;
  dialogs: ReactNode;
}

export interface OwnerRail {
  conversationId: string;
  strategy: StrategyActions;
  openStudy: () => void;
}

export interface RailSource {
  key: string;
  siteId: string;
  strategy: Strategy | null;
  privateInputs: Readonly<Record<string, readonly string[]>>;
  study: EdaAnalysisSnapshot | null;
  activeTasks: readonly TaskListItem[];
  owner: OwnerRail | null;
}
