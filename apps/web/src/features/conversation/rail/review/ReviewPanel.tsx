"use client";

import type { Strategy } from "@strategist/shared";
import { useQuery } from "@tanstack/react-query";
import { runningPhase } from "@veupathdb/assistant-client";
import { ListChecks } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";

import { useEntrance, usePrefersReducedMotion } from "@/lib/motion";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { useConversationExists } from "@/state/useConversationExists";

import { isActiveTask, tasksListOptions } from "../../api/tasks";
import {
  cardIsSuperseded,
  latestEvidenceCard,
} from "../../content/evidence/evidenceCards";
import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { RailEmptyState, RailPanelShell } from "../RailPanelShell";
import { BuildProblems } from "./BuildProblems";
import { CaveatList } from "./CaveatList";
import { ChoiceList } from "./ChoiceList";
import { MemoryFold } from "./MemoryFold";
import { NotesFold } from "./NotesFold";
import { latestLedgerView } from "./readLedger";
import { RequirementList } from "./RequirementList";
import { REVIEW_LIST, ReviewSection } from "./ReviewSection";
import { ReviewVerdict } from "./ReviewVerdict";
import { reviewModel } from "./reviewModel";
import { SpotCheck } from "./SpotCheck";
import { WorkingNow } from "./WorkingNow";

interface ReviewPanelProps {
  conversationId: string;
  strategy: Strategy | null;
}

export function ReviewPanel({ conversationId, strategy }: ReviewPanelProps) {
  const messages = useChatHelpers().messages;
  const exists = useConversationExists(conversationId);
  const tasks = (
    useQuery({ ...tasksListOptions(conversationId), enabled: exists }).data?.tasks ?? []
  ).filter((t) => isActiveTask(t.status));
  const reduced = usePrefersReducedMotion();
  const slide = useEntrance({
    initial: { height: 0, opacity: 0 },
    exit: { height: 0, opacity: 0 },
    transition: { type: "spring", stiffness: 420, damping: 40 },
  });
  const root = strategy?.steps.find((step) => step.id === strategy.rootStepId) ?? null;
  const rootSize = useStepSnapshot(root).estimatedSize;
  const parts = messages.flatMap((m) => m.parts);
  const card = latestEvidenceCard(parts);
  const phase = runningPhase(parts);
  const model = reviewModel({
    ledger: latestLedgerView(messages),
    card,
    superseded: card !== null && cardIsSuperseded(parts, card),
    runningPhase: phase,
    strategy,
    rootCount: typeof rootSize === "number" ? rootSize : null,
  });
  const working = phase !== null || tasks.length > 0;
  return (
    <RailPanelShell title="Review">
      <AnimatePresence initial={false}>
        {working && (
          <motion.div
            key="working"
            {...slide}
            animate={{ height: "auto", opacity: 1 }}
            className="overflow-hidden"
          >
            <WorkingNow phase={phase} tasks={tasks} />
          </motion.div>
        )}
      </AnimatePresence>
      <motion.div
        data-testid="review-panel"
        variants={REVIEW_LIST}
        initial={reduced ? false : "hidden"}
        animate="shown"
      >
        {model.verdict.kind === "empty" ? (
          <div className="border-b border-border py-8">
            <RailEmptyState
              icon={<ListChecks className="size-8" aria-hidden />}
              heading={model.verdict.title}
              description={model.verdict.detail ?? ""}
            />
          </div>
        ) : (
          <>
            {model.question !== null && (
              <ReviewSection title="Your question">
                <p className="text-sm leading-relaxed text-foreground">
                  {model.question}
                </p>
              </ReviewSection>
            )}
            <ReviewSection>
              <ReviewVerdict verdict={model.verdict} />
              <RequirementList rows={model.requirements} />
            </ReviewSection>
            <BuildProblems problems={model.buildProblems} />
            <SpotCheck check={model.spotCheck} />
            <ChoiceList choices={model.choices} />
            <CaveatList caveats={model.caveats} />
          </>
        )}
        <NotesFold conversationId={conversationId} />
        <MemoryFold messages={messages} />
      </motion.div>
    </RailPanelShell>
  );
}
