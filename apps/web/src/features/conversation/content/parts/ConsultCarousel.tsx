"use client";

import type { ConsultQuestion } from "@pathfinder/shared/generated/types/ConsultQuestion";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronLeft, ChevronRight, HelpCircle, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import type { ChatHelpers } from "../../runtime/chatHelpersContext";
import { handleConsultSkip, handleConsultSubmit } from "../../rail/consultActions";
import {
  type AnswerState,
  type ConsultDraft,
  allAnswered,
  answersOf,
  isAnswered,
  movedTo,
  toggled,
  withNote,
} from "./consultDraft";
import type { PendingConsult } from "./consultData";

const SLIDE_TRANSITION = { duration: 0.22, ease: [0.4, 0, 0.2, 1] } as const;

export function ConsultCarousel({
  pending,
  chat,
  draft,
  onDraft,
}: {
  pending: PendingConsult;
  chat: ChatHelpers;
  draft: ConsultDraft;
  onDraft: (draft: ConsultDraft) => void;
}) {
  const questions = pending.questions;
  const { index, direction } = draft;
  const entrance = useEntrance({
    initial: { opacity: 0, x: direction * 24 },
    exit: { opacity: 0, x: direction * -24 },
    transition: SLIDE_TRANSITION,
  });

  const q = questions[index];
  const current = q ? draft.answers[q.id] : undefined;
  const currentAnswered = q ? isAnswered(q, current) : true;
  const isLast = index >= questions.length - 1;

  const go = (next: number) => onDraft(movedTo(draft, questions, next));

  return (
    <div
      data-testid="consult-carousel"
      className="space-y-2 rounded-lg border border-border bg-card/60 p-2"
    >
      <div className="flex items-center gap-2 px-1 text-sm font-medium">
        <HelpCircle className="size-4 text-muted-foreground" aria-hidden />A few
        questions before I build the plan
        <span
          data-testid="consult-place"
          className="ml-auto text-[0.625rem] text-muted-foreground tabular-nums"
        >
          {index + 1} of {questions.length}
        </span>
      </div>

      <div className="rounded-md border border-border bg-background/60 p-2.5">
        <div className="mb-2 flex items-center gap-1.5">
          {questions.map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === index ? "w-5 bg-primary" : "w-1.5 bg-muted-foreground/30",
              )}
            />
          ))}
        </div>

        <div className="relative overflow-hidden">
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            <motion.div
              key={index}
              custom={direction}
              {...entrance}
              animate={{ opacity: 1, x: 0 }}
            >
              {q ? (
                <ConsultSlide
                  question={q}
                  answer={current}
                  onToggle={(label) => onDraft(toggled(draft, q, label))}
                  onNote={(note) => onDraft(withNote(draft, q, note))}
                />
              ) : null}
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="mt-2.5 flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={index === 0}
            onClick={() => go(index - 1)}
            data-testid="consult-back"
          >
            <ChevronLeft className="size-4" aria-hidden /> Back
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="ml-auto text-muted-foreground"
            onClick={() => handleConsultSkip(chat, pending)}
            data-testid="consult-skip"
          >
            Skip these questions
          </Button>
          {isLast ? (
            <Button
              type="button"
              size="sm"
              disabled={!allAnswered(questions, draft)}
              onClick={() =>
                handleConsultSubmit(chat, pending, answersOf(questions, draft))
              }
              data-testid="consult-submit"
            >
              <Check className="mr-1 size-4" aria-hidden /> Submit
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              disabled={!currentAnswered}
              onClick={() => go(index + 1)}
              data-testid="consult-next"
            >
              Next <ChevronRight className="ml-1 size-4" aria-hidden />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function ConsultSlide({
  question,
  answer,
  onToggle,
  onNote,
}: {
  question: ConsultQuestion;
  answer: AnswerState | undefined;
  onToggle: (label: string) => void;
  onNote: (note: string) => void;
}) {
  const chosen = answer?.labels ?? [];
  return (
    <div data-testid="consult-slide" className="space-y-2">
      <p className="text-sm font-medium text-foreground">{question.prompt}</p>
      {question.context != null && question.context !== "" && (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {question.context}
        </p>
      )}
      {question.kind !== "free_text" && (
        <div className="space-y-1.5">
          {(question.options ?? []).map((opt) => {
            const isChosen = chosen.includes(opt.label);
            return (
              <button
                key={opt.label}
                type="button"
                onClick={() => onToggle(opt.label)}
                aria-label={opt.label}
                aria-pressed={isChosen}
                data-testid={`consult-option-${opt.label}`}
                className={cn(
                  "w-full rounded-md border p-2.5 text-left transition-colors",
                  isChosen
                    ? "border-primary bg-primary/10"
                    : "border-border bg-card/60 hover:bg-muted/50",
                )}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "flex size-4 shrink-0 items-center justify-center rounded-full border",
                      isChosen
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-muted-foreground/40",
                    )}
                  >
                    {isChosen && <Check className="size-3" aria-hidden />}
                  </span>
                  <span className="text-xs font-medium text-foreground">
                    {opt.label}
                  </span>
                  {opt.recommended === true && (
                    <span className="ml-auto inline-flex items-center gap-1 rounded bg-success/15 px-1.5 py-0.5 text-[0.5625rem] uppercase tracking-wide text-success">
                      <Sparkles className="size-2.5" aria-hidden /> Recommended
                    </span>
                  )}
                </div>
                {opt.description != null && opt.description !== "" && (
                  <p className="mt-1 pl-6 text-[0.6875rem] text-muted-foreground">
                    {opt.description}
                  </p>
                )}
              </button>
            );
          })}
        </div>
      )}
      {(question.allowNotes !== false || question.kind === "free_text") && (
        <Textarea
          value={answer?.note ?? ""}
          onChange={(e) => onNote(e.target.value)}
          placeholder={
            question.kind === "free_text"
              ? "Your answer..."
              : "Add a comment (optional)..."
          }
          rows={2}
          aria-label={question.kind === "free_text" ? "Your answer" : "Add a comment"}
          data-testid="consult-note"
        />
      )}
    </div>
  );
}
