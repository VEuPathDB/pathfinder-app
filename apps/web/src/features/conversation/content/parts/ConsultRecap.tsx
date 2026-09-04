"use client";

import { HelpCircle } from "lucide-react";

import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";

import type { ConsultRecap } from "./consultData";

function answerText(answer: UserQuestionAnswer | undefined): string {
  if (answer === undefined) return "-";
  const note = answer.note ?? "";
  const labels = answer.chosenLabels ?? [];
  if (labels.length === 0) return note === "" ? "-" : note;
  const chosen = labels.join(", ");
  return note === "" ? chosen : `${chosen} (${note})`;
}

export function ConsultRecapView({ recap }: { recap: ConsultRecap }) {
  const answerByQuestion = new Map(recap.answers.map((a) => [a.questionId, a]));
  return (
    <div
      data-testid="consult-recap"
      className="space-y-2 rounded-lg border border-border bg-card/60 p-2"
    >
      <div className="flex items-center gap-2 px-1 text-sm font-medium">
        <HelpCircle className="size-4 text-muted-foreground" aria-hidden />
        Your answers
      </div>
      <ul
        data-testid="consult-recap-pairs"
        className="space-y-3 rounded-md border border-border bg-background/60 p-2.5 text-xs"
      >
        {recap.questions.map((q) => (
          <li key={q.id} className="space-y-1 leading-snug">
            <p data-testid="consult-recap-question" className="text-foreground">
              <span className="font-medium text-muted-foreground">Q:</span> {q.prompt}
            </p>
            <p data-testid="consult-recap-answer" className="text-foreground">
              <span className="font-medium text-muted-foreground">A:</span>{" "}
              {answerText(answerByQuestion.get(q.id))}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
