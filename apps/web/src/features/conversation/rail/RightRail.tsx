"use client";

import { FlaskConical, ListChecks, Workflow } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Fragment, useState } from "react";
import { createPortal } from "react-dom";

import type { Strategy } from "@pathfinder/shared";
import { Button } from "@/components/ui/button";
import { NarrowBackdrop } from "@/lib/components/NarrowBackdrop";
import { RailFoot } from "@/lib/components/RailFoot";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { viewportIsNarrow } from "@/lib/layout/viewport";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";
import { useChatHelpers } from "../runtime/chatHelpersContext";
import { shouldAutoOpenReview } from "./autoOpenReview";
import {
  lastSeenFor,
  useRightRailStore,
  type RightRailPanel,
} from "@/state/useRightRailStore";
import { useEdaStore } from "@/state/eda";
import { usePhoneBarStore } from "@/state/usePhoneBarStore";
import { useSettingsModalStore } from "@/state/useSettingsModalStore";

import {
  cardIsSuperseded,
  latestEvidenceCard,
} from "../content/evidence/evidenceCards";
import { computeRailActivity } from "./railActivity";
import { RAIL_PANEL_WIDTH } from "./railLayout";
import { EdaPanel } from "./EdaPanel";
import { ReviewPanel } from "./review/ReviewPanel";
import { StrategyPanel } from "./StrategyPanel";

const PANEL_TRANSITION = { type: "spring", stiffness: 380, damping: 36 } as const;

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
  { id: "review", icon: ListChecks, label: "Review" },
  { id: "study", icon: FlaskConical, label: "Study" },
];

const HIGHLIGHT_TRANSITION = { type: "spring", stiffness: 520, damping: 40 } as const;

export function RightRail({ conversationId, strategy, siteId }: RightRailProps) {
  const openPanel = useRightRailStore((s) => s.openPanel);
  const lastSeen = lastSeenFor(
    useRightRailStore((s) => s.lastSeen),
    conversationId,
  );
  const togglePanel = useRightRailStore((s) => s.togglePanel);
  const closePanel = useRightRailStore((s) => s.closePanel);
  const phoneSlot = usePhoneBarStore((s) => s.slot);
  const autoOpenedConversation = useRightRailStore((s) => s.autoOpenedConversation);
  const autoOpen = useRightRailStore((s) => s.autoOpen);
  const openSettings = useSettingsModalStore((s) => s.open);
  const studyOpen = useEdaStore((s) => s.analysis) !== null;

  const strategyStepCount = strategy?.steps.length ?? 0;
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
  const highlight = useEntrance({
    initial: { opacity: 0 },
    exit: { opacity: 0 },
    transition: HIGHLIGHT_TRANSITION,
  });
  const dotEntrance = useEntrance({
    initial: { scale: 0, opacity: 0 },
    exit: { scale: 0, opacity: 0 },
    transition: { type: "spring", stiffness: 500, damping: 24 },
  });
  if (
    shouldAutoOpenReview({
      hasUserMessage: activity.hasUserMessage,
      conversationId,
      autoOpenedConversation,
      autoOpenChecked,
      narrowViewport: viewportIsNarrow(),
    })
  ) {
    setAutoOpenChecked(conversationId);
    queueMicrotask(() => autoOpen(conversationId, "review"));
  }

  const hasUpdate: Record<RightRailPanel, boolean> = {
    strategy: strategyStepCount !== lastSeen.strategyStepCount,
    review: activity.reviewCount !== lastSeen.reviewCount,
    study: activity.studyCount !== lastSeen.studyCount,
  };

  const markersFor = (panel: RightRailPanel): Partial<typeof lastSeen> => {
    switch (panel) {
      case "strategy":
        return { strategyStepCount };
      case "review":
        return { reviewCount: activity.reviewCount };
      case "study":
        return { studyCount: activity.studyCount };
    }
  };

  const shownIcons = RAIL_ICONS.filter(
    ({ id }) =>
      id !== "study" || studyOpen || activity.studyCount > 0 || openPanel === "study",
  );

  const button = (
    id: RightRailPanel,
    Icon: LucideIcon,
    label: string,
    onPhone: boolean,
  ) => {
    const isOpen = openPanel === id;
    const showDot = hasUpdate[id] && !isOpen;
    return (
      <Button
        variant="ghost"
        size="icon"
        onClick={() => togglePanel(conversationId, id, markersFor(id))}
        aria-label={`${isOpen ? "Close" : "Open"} ${label}`}
        aria-pressed={isOpen}
        className={cn(
          "relative transition-transform active:scale-[0.98]",
          onPhone && "size-11 shrink-0",
          isOpen && "text-primary hover:bg-transparent hover:text-primary",
        )}
      >
        {isOpen && (
          <motion.span
            layoutId={`rail-active-${onPhone ? "phone" : "rail"}`}
            {...highlight}
            animate={{ opacity: 1 }}
            aria-hidden
            className="absolute inset-0 rounded-md bg-primary/15"
          />
        )}
        <Icon className="relative h-4 w-4" aria-hidden />
        <AnimatePresence>
          {showDot && (
            <motion.span
              key="dot"
              {...dotEntrance}
              animate={{ scale: 1, opacity: 1 }}
              aria-label={`${label} has updates`}
              className="absolute right-1 top-1 h-2 w-2 rounded-full bg-primary"
            />
          )}
        </AnimatePresence>
      </Button>
    );
  };

  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delayDuration={150}>
        {openPanel != null && (
          <NarrowBackdrop
            label="Close panel"
            onClose={closePanel}
            className="left-0 right-11 max-sm:right-0"
          />
        )}
        <AnimatePresence initial={false}>
          {openPanel != null && (
            <motion.div
              key="rail-panel"
              data-testid="rail-panel"
              {...panelEntrance}
              animate={{ width: RAIL_PANEL_WIDTH, opacity: 1 }}
              className="h-full shrink-0 overflow-hidden border-l border-border bg-background max-[900px]:absolute max-[900px]:inset-y-0 max-[900px]:right-11 max-[900px]:z-40 max-[900px]:max-w-[calc(100%-5.75rem)] max-sm:right-0 max-sm:max-w-[calc(100%-3rem)] max-[900px]:shadow-xl"
            >
              <div
                style={{ width: RAIL_PANEL_WIDTH }}
                className="h-full max-[900px]:w-full!"
              >
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={openPanel}
                    {...bodyEntrance}
                    animate={{ opacity: 1, y: 0 }}
                    className="h-full"
                  >
                    {openPanel === "strategy" && (
                      <StrategyPanel
                        strategy={strategy}
                        siteId={siteId}
                        conversationId={conversationId}
                        check={check}
                      />
                    )}
                    {openPanel === "review" && (
                      <ReviewPanel
                        conversationId={conversationId}
                        strategy={strategy}
                      />
                    )}
                    {openPanel === "study" && (
                      <EdaPanel conversationId={conversationId} />
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <div
          role="toolbar"
          aria-orientation="vertical"
          aria-label="Right rail"
          className="flex h-full w-11 shrink-0 flex-col items-center gap-1 border-l border-border bg-sidebar py-2 max-sm:hidden"
        >
          {shownIcons.map(({ id, icon, label }) => (
            <Tooltip key={id}>
              <TooltipTrigger asChild>{button(id, icon, label, false)}</TooltipTrigger>
              <TooltipContent side="left">{label}</TooltipContent>
            </Tooltip>
          ))}
          <RailFoot onOpenSettings={() => openSettings()} />
        </div>
        {phoneSlot !== null &&
          createPortal(
            shownIcons.map(({ id, icon, label }) => (
              <Fragment key={id}>{button(id, icon, label, true)}</Fragment>
            )),
            phoneSlot,
          )}
      </TooltipProvider>
    </MotionConfig>
  );
}
