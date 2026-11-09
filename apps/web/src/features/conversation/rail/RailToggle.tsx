"use client";

import type { Strategy } from "@pathfinder/shared";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Fragment, useId } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";
import { usePhoneBarStore } from "@/state/usePhoneBarStore";

import { ShareButton } from "../share/ShareButton";
import { useRailPanels, type RailPanelButton } from "./useRailPanels";

const HIGHLIGHT = { type: "spring", stiffness: 520, damping: 40 } as const;

interface RailToggleProps {
  conversationId: string;
  strategy: Strategy | null;
}

function PanelButton({ panel, onPhone }: { panel: RailPanelButton; onPhone: boolean }) {
  const highlight = useEntrance({
    initial: { opacity: 0 },
    exit: { opacity: 0 },
    transition: HIGHLIGHT,
  });
  const dot = useEntrance({
    initial: { scale: 0, opacity: 0 },
    exit: { scale: 0, opacity: 0 },
    transition: { type: "spring", stiffness: 500, damping: 24 },
  });
  const Icon = panel.icon;
  const dotId = useId();
  const showDot = panel.hasUpdate && !panel.open;
  return (
    <Button
      variant="ghost"
      size={onPhone ? "icon" : "sm"}
      onClick={panel.toggle}
      aria-label={`${panel.open ? "Close" : "Open"} ${panel.label}`}
      aria-pressed={panel.open}
      aria-describedby={showDot ? dotId : undefined}
      className={cn(
        "relative transition-transform active:scale-[0.98]",
        onPhone ? "size-11 shrink-0" : "h-7 gap-1.5 rounded-full px-2.5 text-xs",
        panel.open && "text-primary hover:bg-transparent hover:text-primary",
      )}
    >
      {panel.open && (
        <motion.span
          layoutId={`rail-active-${onPhone ? "phone" : "pill"}`}
          {...highlight}
          animate={{ opacity: 1 }}
          aria-hidden
          className={cn(
            "absolute inset-0 bg-primary/15",
            onPhone ? "rounded-md" : "rounded-full",
          )}
        />
      )}
      <Icon className="relative size-3.5" aria-hidden />
      {!onPhone && <span className="relative">{panel.label}</span>}
      <AnimatePresence>
        {showDot && (
          <motion.span
            key="dot"
            id={dotId}
            {...dot}
            animate={{ scale: 1, opacity: 1 }}
            className={cn(
              "absolute size-1.5 rounded-full bg-primary",
              onPhone ? "right-1.5 top-1.5" : "right-1 top-0.5",
            )}
          >
            <span className="sr-only">{panel.label} has updates</span>
          </motion.span>
        )}
      </AnimatePresence>
    </Button>
  );
}

export function RailToggle({ conversationId, strategy }: RailToggleProps) {
  const panels = useRailPanels(conversationId, strategy);
  const phoneSlot = usePhoneBarStore((s) => s.slot);
  return (
    <MotionConfig reducedMotion="user">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 z-10 h-12 bg-gradient-to-b from-card via-card/80 to-transparent max-sm:hidden"
      />
      <div className="absolute right-3 top-3 z-20 flex items-center gap-1.5 max-sm:hidden">
        <ShareButton conversationId={conversationId} onPhone={false} />
        <div
          role="toolbar"
          aria-label="Side panels"
          className="flex items-center gap-0.5 rounded-full border border-border bg-background/85 p-0.5 shadow-sm backdrop-blur"
        >
          {panels.map((panel) => (
            <PanelButton key={panel.id} panel={panel} onPhone={false} />
          ))}
        </div>
      </div>
      {phoneSlot !== null &&
        createPortal(
          <>
            {panels.map((panel) => (
              <Fragment key={panel.id}>
                <PanelButton panel={panel} onPhone />
              </Fragment>
            ))}
            <ShareButton conversationId={conversationId} onPhone />
          </>,
          phoneSlot,
        )}
    </MotionConfig>
  );
}
