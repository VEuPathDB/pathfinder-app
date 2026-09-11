"use client";

import { useAuiState } from "@assistant-ui/react";
import type { ConsultQuestion } from "@pathfinder/shared/generated/types/ConsultQuestion";
import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";
import { AnimatePresence, motion } from "motion/react";
import { Check, ChevronLeft, ChevronRight, HelpCircle, Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useEntrance } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

import { useChatHelpers, type ChatHelpers } from "../../runtime/chatHelpersContext";
import { handleConsultSubmit } from "../../rail/consultActions";
import { ConsultRecapView } from "./ConsultRecap";
import {
  type PendingConsult,
  findConsultRecap,
  findPendingConsult,
} from "./consultData";

interface AnswerState {
  labels: string[];
  note: string;
}

const SLIDE_TRANSITION = { duration: 0.22, ease: [0.4, 0, 0.2, 1] } as const;

export function ConsultCarousel({ toolCallId }: { toolCallId?: string }) {
  const currentId = useAuiState((s) => s.message.id);
  const chat = useChatHelpers();
  const message = chat.messages.find((m) => m.id === currentId);
  if (message?.role !== "assistant") return null;
  if (toolCallId !== undefined) {
    const first = message.parts.find((part) => part.type === "tool-consult_user");
    if (first == null || !("toolCallId" in first) || first.toolCallId !== toolCallId) {
      return null;
    }
  }
  const pending = findPendingConsult(message);
  if (pending !== null && pending.questions.length > 0) {
    return <ConsultCarouselView pending={pending} chat={chat} />;
  }
  const recap = findConsultRecap(message);
  if (recap !== null && recap.questions.length > 0) {
    return <ConsultRecapView recap={recap} />;
  }
  return null;
}

function isAnswered(q: ConsultQuestion, a: AnswerState | undefined): boolean {
  if (a === undefined) return false;
  if (q.kind === "free_text") return a.note.trim() !== "";
  return a.labels.length > 0;
}

export function ConsultCarouselView({
  pending,
  chat,
}: {
  pending: PendingConsult;
  chat: ChatHelpers;
}) {
  const questions = pending.questions;
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const entrance = useEntrance({
    initial: { opacity: 0, x: direction * 24 },
    exit: { opacity: 0, x: direction * -24 },
    transition: SLIDE_TRANSITION,
  });

  const q = questions[index];
  const current = q ? answers[q.id] : undefined;
  const currentAnswered = q ? isAnswered(q, current) : true;
  const allAnswered = questions.every((qq) => isAnswered(qq, answers[qq.id]));
  const isLast = index >= questions.length - 1;

  const go = (next: number) => {
    setDirection(next > index ? 1 : -1);
    setIndex(Math.max(0, Math.min(next, questions.length - 1)));
  };

  const toggle = (question: ConsultQuestion, label: string) => {
    setAnswers((prev) => {
      const a = prev[question.id] ?? { labels: [], note: "" };
      if (question.kind === "multi_choice") {
        const labels = a.labels.includes(label)
          ? a.labels.filter((l) => l !== label)
          : [...a.labels, label];
        return { ...prev, [question.id]: { ...a, labels } };
      }
      return { ...prev, [question.id]: { ...a, labels: [label] } };
    });
  };

  const setNote = (question: ConsultQuestion, note: string) => {
    setAnswers((prev) => {
      const a = prev[question.id] ?? { labels: [], note: "" };
      return { ...prev, [question.id]: { ...a, note } };
    });
  };

  const submit = () => {
    const entries: UserQuestionAnswer[] = questions.map((qq) => {
      const a = answers[qq.id] ?? { labels: [], note: "" };
      return {
        questionId: qq.id,
        prompt: qq.prompt,
        chosenLabels: a.labels,
        note: a.note,
      };
    });
    handleConsultSubmit(chat, pending, entries);
  };

  return (
    <div
      data-testid="consult-carousel"
      className="space-y-2 rounded-lg border border-border bg-card/60 p-2"
    >
      <div className="flex items-center gap-2 px-1 text-sm font-medium">
        <HelpCircle className="size-4 text-muted-foreground" aria-hidden />A few
        questions before I build the plan
        <span className="ml-auto text-[10px] text-muted-foreground tabular-nums">
          {index + 1} / {questions.length}
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
                  onToggle={(label) => toggle(q, label)}
                  onNote={(note) => setNote(q, note)}
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
          {isLast ? (
            <Button
              type="button"
              size="sm"
              className="ml-auto"
              disabled={!allAnswered}
              onClick={submit}
              data-testid="consult-submit"
            >
              <Check className="mr-1 size-4" aria-hidden /> Submit
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              className="ml-auto"
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
                    <span className="ml-auto inline-flex items-center gap-1 rounded bg-success/15 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-success">
                      <Sparkles className="size-2.5" aria-hidden /> Recommended
                    </span>
                  )}
                </div>
                {opt.description != null && opt.description !== "" && (
                  <p className="mt-1 pl-6 text-[11px] text-muted-foreground">
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
              : "Add a note (optional)..."
          }
          rows={2}
          aria-label={question.kind === "free_text" ? "Your answer" : "Add a note"}
          data-testid="consult-note"
        />
      )}
    </div>
  );
}
