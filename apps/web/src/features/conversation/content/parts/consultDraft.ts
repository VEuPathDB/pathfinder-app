import type { ConsultQuestion } from "@pathfinder/shared/generated/types/ConsultQuestion";
import type { UserQuestionAnswer } from "@pathfinder/shared/generated/types/UserQuestionAnswer";

export interface AnswerState {
  labels: string[];
  note: string;
}

export interface ConsultDraft {
  index: number;
  direction: number;
  answers: Record<string, AnswerState>;
}

export const EMPTY_DRAFT: ConsultDraft = { index: 0, direction: 1, answers: {} };

const NO_ANSWER: AnswerState = { labels: [], note: "" };

function answerOf(draft: ConsultDraft, question: ConsultQuestion): AnswerState {
  return draft.answers[question.id] ?? NO_ANSWER;
}

function withAnswer(
  draft: ConsultDraft,
  question: ConsultQuestion,
  answer: AnswerState,
): ConsultDraft {
  return { ...draft, answers: { ...draft.answers, [question.id]: answer } };
}

export function isAnswered(
  question: ConsultQuestion,
  answer: AnswerState | undefined,
): boolean {
  if (answer === undefined) return false;
  const typed = answer.note.trim() !== "";
  return question.kind === "free_text" ? typed : typed || answer.labels.length > 0;
}

export function allAnswered(
  questions: readonly ConsultQuestion[],
  draft: ConsultDraft,
): boolean {
  return questions.every((question) =>
    isAnswered(question, draft.answers[question.id]),
  );
}

export function movedTo(
  draft: ConsultDraft,
  questions: readonly ConsultQuestion[],
  next: number,
): ConsultDraft {
  return {
    ...draft,
    direction: next > draft.index ? 1 : -1,
    index: Math.max(0, Math.min(next, questions.length - 1)),
  };
}

export function toggled(
  draft: ConsultDraft,
  question: ConsultQuestion,
  label: string,
): ConsultDraft {
  const answer = answerOf(draft, question);
  if (question.kind !== "multi_choice") {
    return withAnswer(draft, question, { ...answer, labels: [label] });
  }
  const labels = answer.labels.includes(label)
    ? answer.labels.filter((each) => each !== label)
    : [...answer.labels, label];
  return withAnswer(draft, question, { ...answer, labels });
}

export function withNote(
  draft: ConsultDraft,
  question: ConsultQuestion,
  note: string,
): ConsultDraft {
  return withAnswer(draft, question, { ...answerOf(draft, question), note });
}

export function typedAnswer(
  questions: readonly ConsultQuestion[],
  draft: ConsultDraft,
  text: string,
): ConsultDraft {
  const current = questions[draft.index];
  if (current === undefined) return draft;
  const answered = withNote(draft, current, text);
  const open = questions.findIndex(
    (question) => !isAnswered(question, answered.answers[question.id]),
  );
  return open === -1 ? answered : movedTo(answered, questions, open);
}

export function answersOf(
  questions: readonly ConsultQuestion[],
  draft: ConsultDraft,
): UserQuestionAnswer[] {
  return questions.map((question) => {
    const answer = answerOf(draft, question);
    return {
      questionId: question.id,
      prompt: question.prompt,
      chosenLabels: answer.labels,
      note: answer.note,
    };
  });
}
