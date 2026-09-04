import type { FunctionComponent } from "react";

import { SubAgentTraceAnchor } from "../thread/TraceAnchor";
import { DataBackgroundTaskStarted } from "./parts/DataBackgroundTaskStarted";
import { DataMemoryRetrieved } from "./parts/DataMemoryRetrieved";
import { DataTurnFailed } from "./parts/DataTurnFailed";
import { DataTurnStopped } from "./parts/DataTurnStopped";
import type { DataPartComponentMap } from "./dataPartComponentMap";

/**
 * The one component every non-drawing kind points at. Its identity is what
 * tells the trace which kinds are figures, so the two can never disagree.
 */
export const noRender: FunctionComponent<{ data: unknown }> = () => null;

/** Parts any assistant emits: turn state, usage, tasks, sub-agents, memory. */
export type CoreDataPartKind =
  | "data-sub-agent-call"
  | "data-sub-agent-step"
  | "data-background-task-started"
  | "data-task-progress"
  | "data-task-completed"
  | "data-memory-retrieved"
  | "data-conversation-title"
  | "data-scratchpad-updated"
  | "data-turn-usage"
  | "data-turn-status"
  | "data-turn-stopped"
  | "data-turn-failed"
  | "data-lead-usage"
  | "data-tool-summary"
  | "data-user-question-answers";

export const coreDataPartComponents: DataPartComponentMap<CoreDataPartKind> = {
  "data-sub-agent-call": SubAgentTraceAnchor,
  "data-sub-agent-step": noRender,
  "data-background-task-started": DataBackgroundTaskStarted,
  // The task row renders a task's progress and outcome from the message.
  "data-task-progress": noRender,
  "data-task-completed": noRender,
  "data-memory-retrieved": DataMemoryRetrieved,
  "data-conversation-title": noRender,
  "data-scratchpad-updated": noRender,
  "data-turn-usage": noRender,
  "data-turn-status": noRender,
  "data-turn-stopped": DataTurnStopped,
  "data-turn-failed": DataTurnFailed,
  "data-lead-usage": noRender,
  // The trace reads the line; the thread never draws it as a part of its own.
  "data-tool-summary": noRender,
  // The consult answers travel back to the backend and draw nothing.
  "data-user-question-answers": noRender,
};
