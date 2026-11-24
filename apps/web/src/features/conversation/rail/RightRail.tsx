"use client";

import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useState } from "react";

import { NarrowBackdrop } from "@/lib/components/NarrowBackdrop";
import { RIGHT_PANEL_WIDTH_PX } from "@/lib/layout/dock";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";
import {
  railMayOpenItself,
  useDockLayout,
  useLeftSidebarDrawn,
} from "@/state/useDockLayout";
import { useRightRailStore } from "@/state/useRightRailStore";

import {
  cardIsSuperseded,
  latestEvidenceCard,
} from "../content/evidence/evidenceCards";
import { useChatHelpers } from "../runtime/chatHelpersContext";
import { shouldAutoOpenReview } from "./autoOpenReview";
import { EdaPanel } from "./EdaPanel";
import { computeRailActivity } from "./railActivity";
import type { RailSource } from "./railSource";
import { ReviewPanel } from "./review/ReviewPanel";
import { StrategyPanel } from "./StrategyPanel";

const PANEL_TRANSITION = { type: "spring", stiffness: 380, damping: 36 } as const;

export function RightRail({ source }: { source: RailSource }) {
  const openPanel = useRightRailStore((s) => s.openPanel);
  const closePanel = useRightRailStore((s) => s.closePanel);
  const autoOpenedConversation = useRightRailStore((s) => s.autoOpenedConversation);
  const autoOpen = useRightRailStore((s) => s.autoOpen);
  const { rightFloats } = useDockLayout();
  const leftDrawn = useLeftSidebarDrawn();
  const chat = useChatHelpers();
  const activity = computeRailActivity(chat.messages);
  const parts = chat.messages.flatMap((m) => m.parts);
  const card = latestEvidenceCard(parts);
  const check =
    card === null ? null : { card, superseded: cardIsSuperseded(parts, card) };

  const [autoOpenChecked, setAutoOpenChecked] = useState<string | null>(null);
  const panelEntrance = useEntrance({
    initial: { width: 0, opacity: 0 },
    exit: { width: 0, opacity: 0 },
    transition: PANEL_TRANSITION,
  });
  const bodyEntrance = useEntrance({
    initial: { opacity: 0, y: 4 },
    exit: { opacity: 0, y: -4 },
    transition: { duration: 0.15 },
  });
  if (
    shouldAutoOpenReview({
      hasUserMessage: activity.hasUserMessage,
      conversationId: source.key,
      autoOpenedConversation,
      autoOpenChecked,
    }) &&
    railMayOpenItself(leftDrawn)
  ) {
    setAutoOpenChecked(source.key);
    queueMicrotask(() => autoOpen(source.key, "review"));
  }

  return (
    <MotionConfig reducedMotion="user">
      {openPanel != null && rightFloats && (
        <NarrowBackdrop
          label="Close panel"
          onClose={closePanel}
          className="inset-x-0"
        />
      )}
      <AnimatePresence initial={false}>
        {openPanel != null && (
          <motion.div
            key="rail-panel"
            data-testid="rail-panel"
            {...panelEntrance}
            animate={{ width: RIGHT_PANEL_WIDTH_PX, opacity: 1 }}
            className={cn(
              "h-full shrink-0 overflow-hidden border-l border-border bg-background",
              rightFloats &&
                "absolute inset-y-0 right-0 z-40 max-w-[calc(100%-3rem)] shadow-xl",
            )}
          >
            <div
              style={{ width: RIGHT_PANEL_WIDTH_PX }}
              className={cn("h-full", rightFloats && "w-full!")}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={openPanel}
                  {...bodyEntrance}
                  animate={{ opacity: 1, y: 0 }}
                  className="h-full"
                >
                  {openPanel === "strategy" && (
                    <StrategyPanel source={source} check={check} />
                  )}
                  {openPanel === "review" && <ReviewPanel source={source} />}
                  {openPanel === "study" && <EdaPanel source={source} />}
                </motion.div>
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}
