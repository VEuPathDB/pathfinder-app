"use client";

import { AuiIf, ThreadPrimitive } from "@assistant-ui/react";
import { motion } from "motion/react";
import { Settings2, X } from "lucide-react";

import { siteDisplayName } from "@pathfinder/shared";

import suggestedQuestions from "@/features/conversation/data/suggestedQuestions.json";
import {
  DEFAULT_ASSISTANT_ID,
  assistantChoice,
  assistantLabel,
} from "@/lib/assistants";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";
import { useSessionStore } from "@/state/useSessionStore";
import { useSettingsStore } from "@/state/useSettingsStore";

type SuggestionsBySite = Record<string, readonly string[] | undefined>;

function suggestionsForSite(siteId: string): readonly string[] {
  const bank = suggestedQuestions as SuggestionsBySite;
  return bank[siteId] ?? bank["veupathdb"] ?? [];
}

function greetingForHour(hour: number): string {
  if (hour < 5) return "Still up?";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

const suggestionEase = [0.22, 1, 0.36, 1] as const;

export function ChatEmptyState({ assistantId }: { assistantId: string }) {
  const siteId = useSessionStore((s) => s.selectedSite);
  const displayName = siteDisplayName(siteId);
  const hintDismissed = useSettingsStore((s) => s.firstRunHintDismissed);
  const dismissHint = useSettingsStore((s) => s.dismissFirstRunHint);
  const choice = assistantChoice(assistantId);
  // The suggestion bank asks for strategies, which only the default assistant
  // builds.
  const suggestions =
    assistantId === DEFAULT_ASSISTANT_ID ? suggestionsForSite(siteId) : [];
  const greeting = greetingForHour(new Date().getHours());
  const headingEntrance = useEntrance({
    initial: { opacity: 0, y: 8 },
    transition: { duration: 0.4, ease: suggestionEase, delay: 0.05 },
  });
  const blurbEntrance = useEntrance({
    initial: { opacity: 0, y: 8 },
    transition: { duration: 0.4, ease: suggestionEase, delay: 0.12 },
  });
  const hintEntrance = useEntrance({
    initial: { opacity: 0, y: 8 },
    transition: { duration: 0.4, ease: suggestionEase, delay: 0.2 },
  });

  return (
    <AuiIf condition={(s) => s.thread.isEmpty}>
      <div className="flex min-h-[60vh] flex-1 flex-col items-center justify-center px-6 py-10 text-center">
        {assistantId !== DEFAULT_ASSISTANT_ID && (
          <div
            data-testid="chat-assistant-label"
            className="mb-3 rounded-full border border-border/60 px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground"
          >
            {assistantLabel(assistantId)}
          </div>
        )}
        <motion.h1
          {...headingEntrance}
          animate={{ opacity: 1, y: 0 }}
          className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl"
        >
          {greeting}
        </motion.h1>
        {choice !== null && (
          <motion.p
            {...blurbEntrance}
            animate={{ opacity: 1, y: 0 }}
            className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground"
            data-testid="chat-empty-blurb"
          >
            {choice.blurb(displayName)}
          </motion.p>
        )}

        {!hintDismissed && (
          <motion.div
            {...hintEntrance}
            animate={{ opacity: 1, y: 0 }}
            className="mt-6 flex max-w-md items-center gap-3 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-left text-xs text-muted-foreground"
          >
            <Settings2 className="h-4 w-4 shrink-0 text-primary" aria-hidden />
            <div className="flex-1">
              Running on the default provider + orchestrator. Tweak models, tiers, and
              the orchestrator in{" "}
              <span className="font-medium text-foreground">Settings → AI Engine</span>.
            </div>
            <button
              type="button"
              onClick={dismissHint}
              aria-label="Dismiss hint"
              className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        )}

        {suggestions.length > 0 && (
          <div
            className={cn(
              "mt-8 w-full max-w-3xl",
              "flex gap-2.5 overflow-x-auto pb-1",
              "sm:grid sm:grid-cols-2 sm:overflow-visible",
              "[&::-webkit-scrollbar]:hidden",
            )}
            style={{ scrollbarWidth: "none" }}
          >
            {suggestions.map((prompt, i) => (
              <SuggestionCard key={prompt} prompt={prompt} index={i} />
            ))}
          </div>
        )}
      </div>
    </AuiIf>
  );
}

function SuggestionCard({ prompt, index }: { prompt: string; index: number }) {
  const entrance = useEntrance({
    initial: { opacity: 0, y: 16 },
    transition: { delay: 0.18 + 0.06 * index, duration: 0.4, ease: suggestionEase },
  });

  return (
    <motion.div
      {...entrance}
      animate={{ opacity: 1, y: 0 }}
      className="min-w-[240px] shrink-0 sm:min-w-0 sm:shrink"
    >
      <ThreadPrimitive.Suggestion
        prompt={prompt}
        send
        className={cn(
          "h-auto w-full whitespace-normal rounded-xl border border-border/60 bg-card/40 px-4 py-3",
          "text-left text-[13px] leading-relaxed text-muted-foreground",
          "transition-all duration-200",
          "hover:-translate-y-0.5 hover:bg-card/80 hover:text-foreground hover:shadow-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        {prompt}
      </ThreadPrimitive.Suggestion>
    </motion.div>
  );
}
