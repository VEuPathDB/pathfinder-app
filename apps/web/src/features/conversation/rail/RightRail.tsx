"use client";

import {
  Brain,
  FlaskConical,
  Notebook,
  ScrollText,
  Timer,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";

import type { Strategy } from "@pathfinder/shared";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { viewportIsNarrow } from "@/lib/layout/viewport";
import { cn } from "@/lib/utils/cn";
import { useChatHelpers } from "../runtime/chatHelpersContext";
import { shouldAutoOpenLedger } from "./autoOpenLedger";
import {
  lastSeenFor,
  useRightRailStore,
  type RightRailPanel,
} from "@/state/useRightRailStore";

import { computeRailActivity } from "./railActivity";
import { RAIL_PANEL_WIDTH } from "./railLayout";
import { EdaPanel } from "./EdaPanel";
import { LedgerPanel } from "./LedgerPanel";
import { MemoriesPanel } from "./MemoriesPanel";
import { ScratchpadPanel } from "./ScratchpadPanel";
import { StrategyPanel } from "./StrategyPanel";
import { TasksPanel } from "./TasksPanel";

const PANEL_TRANSITION = { type: "spring", stiffness: 380, damping: 36 } as const;
const ACTIVE_PILL = "bg-primary/15 text-primary hover:bg-primary/20 hover:text-primary";

interface RightRailProps {
  conversationId: string;
  strategy: Strategy | null;
  siteId: string;
}

interface RailIconSpec {
  id: RightRailPanel;
  icon: LucideIcon;
  label: string;
}

const RAIL_ICONS: RailIconSpec[] = [
  { id: "strategy", icon: Workflow, label: "Strategy" },
  { id: "tasks", icon: Timer, label: "Tasks" },
  { id: "memories", icon: Brain, label: "Memories" },
  { id: "scratchpad", icon: Notebook, label: "Scratchpad" },
  { id: "ledger", icon: ScrollText, label: "Progress" },
  { id: "eda", icon: FlaskConical, label: "Studies" },
];

export function RightRail({ conversationId, strategy, siteId }: RightRailProps) {
  const openPanel = useRightRailStore((s) => s.openPanel);
  const lastSeen = lastSeenFor(
    useRightRailStore((s) => s.lastSeen),
    conversationId,
  );
  const togglePanel = useRightRailStore((s) => s.togglePanel);
  const autoOpenedConversation = useRightRailStore((s) => s.autoOpenedConversation);
  const autoOpen = useRightRailStore((s) => s.autoOpen);

  const strategyStepCount = strategy?.steps.length ?? 0;
  const chat = useChatHelpers();
  const activity = computeRailActivity(chat.messages);

  const [autoOpenChecked, setAutoOpenChecked] = useState<string | null>(null);
  if (
    shouldAutoOpenLedger({
      hasUserMessage: activity.hasUserMessage,
      conversationId,
      autoOpenedConversation,
      autoOpenChecked,
      narrowViewport: viewportIsNarrow(),
    })
  ) {
    setAutoOpenChecked(conversationId);
    queueMicrotask(() => autoOpen(conversationId, "ledger"));
  }

  const hasUpdate: Record<RightRailPanel, boolean> = {
    strategy: strategyStepCount !== lastSeen.strategyStepCount,
    tasks: activity.taskCount !== lastSeen.taskCount,
    memories: activity.memoryCount !== lastSeen.memoryCount,
    scratchpad: activity.scratchpadCount !== lastSeen.scratchpadCount,
    ledger: activity.ledgerCount !== lastSeen.ledgerCount,
    eda: activity.edaCount !== lastSeen.edaCount,
  };

  const markersFor = (panel: RightRailPanel): Partial<typeof lastSeen> => {
    switch (panel) {
      case "strategy":
        return { strategyStepCount };
      case "tasks":
        return { taskCount: activity.taskCount };
      case "memories":
        return { memoryCount: activity.memoryCount };
      case "scratchpad":
        return { scratchpadCount: activity.scratchpadCount };
      case "ledger":
        return { ledgerCount: activity.ledgerCount };
      case "eda":
        return { edaCount: activity.edaCount };
    }
  };

  return (
    <TooltipProvider delayDuration={150}>
      <AnimatePresence initial={false}>
        {openPanel != null && (
          <motion.div
            key="rail-panel"
            data-testid="rail-panel"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: RAIL_PANEL_WIDTH, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={PANEL_TRANSITION}
            className="h-full shrink-0 overflow-hidden border-l border-border bg-background"
          >
            <div style={{ width: RAIL_PANEL_WIDTH }} className="h-full">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={openPanel}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.15 }}
                  className="h-full"
                >
                  {openPanel === "strategy" && (
                    <StrategyPanel
                      strategy={strategy}
                      siteId={siteId}
                      conversationId={conversationId}
                    />
                  )}
                  {openPanel === "tasks" && (
                    <TasksPanel conversationId={conversationId} />
                  )}
                  {openPanel === "memories" && <MemoriesPanel />}
                  {openPanel === "scratchpad" && (
                    <ScratchpadPanel conversationId={conversationId} />
                  )}
                  {openPanel === "ledger" && (
                    <LedgerPanel conversationId={conversationId} />
                  )}
                  {openPanel === "eda" && (
                    <EdaPanel conversationId={conversationId} siteId={siteId} />
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <div
        className="flex h-full w-11 shrink-0 flex-col items-center gap-1 border-l border-border bg-sidebar py-2"
        aria-label="Right rail"
      >
        {RAIL_ICONS.map(({ id, icon: Icon, label }) => {
          const isOpen = openPanel === id;
          const showDot = hasUpdate[id] && !isOpen;
          return (
            <Tooltip key={id}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => togglePanel(conversationId, id, markersFor(id))}
                  aria-label={`${isOpen ? "Close" : "Open"} ${label}`}
                  aria-pressed={isOpen}
                  className={cn("relative", isOpen && ACTIVE_PILL)}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  <AnimatePresence>
                    {showDot && (
                      <motion.span
                        key="dot"
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0, opacity: 0 }}
                        transition={{ type: "spring", stiffness: 500, damping: 24 }}
                        aria-label={`${label} has updates`}
                        className="absolute right-1 top-1 h-2 w-2 rounded-full bg-primary"
                      />
                    )}
                  </AnimatePresence>
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">{label}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
