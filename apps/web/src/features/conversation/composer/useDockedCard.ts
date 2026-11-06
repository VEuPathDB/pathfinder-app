"use client";

import { useAui, useAuiState } from "@assistant-ui/react";
import { useState } from "react";

import { openCards, type OpenCard } from "../content/parts/cardAnswers";
import { pendingConsultOf } from "../content/parts/consultData";
import {
  EMPTY_DRAFT,
  allAnswered,
  answersOf,
  takesTypedNotes,
  typedAnswer,
  type ConsultDraft,
} from "../content/parts/consultDraft";
import { CONSULT_TOOL_NAME, handleConsultSubmit } from "../rail/consultActions";
import { useChatHelpers } from "../runtime/chatHelpersContext";
import { parseSlashInput } from "../slash/parser";

export interface DockedCard {
  card: OpenCard | null;
  draft: ConsultDraft;
  setDraft: (draft: ConsultDraft) => void;
  answerTyped: () => boolean;
}

export function useDockedCard(): DockedCard {
  const chat = useChatHelpers();
  const aui = useAui();
  const text = useAuiState((s) => s.composer.text);
  const [drafts, setDrafts] = useState<Record<string, ConsultDraft>>({});
  const card = openCards(chat.messages)[0] ?? null;
  const draft = card === null ? EMPTY_DRAFT : (drafts[card.approvalId] ?? EMPTY_DRAFT);

  const setDraft = (next: ConsultDraft): void => {
    if (card === null) return;
    setDrafts((prev) => ({ ...prev, [card.approvalId]: next }));
  };

  const answerTyped = (): boolean => {
    const typed = text.trim();
    if (card?.toolName !== CONSULT_TOOL_NAME || typed === "") return false;
    if (parseSlashInput(typed) !== null) return false;
    const pending = pendingConsultOf(card);
    if (pending.questions.length === 0) return false;
    if (!takesTypedNotes(pending.questions, draft)) return false;
    const next = typedAnswer(pending.questions, draft, typed);
    if (allAnswered(pending.questions, next)) {
      handleConsultSubmit(chat, pending, answersOf(pending.questions, next));
    } else {
      setDraft(next);
    }
    aui.composer().setText("");
    return true;
  };

  return { card, draft, setDraft, answerTyped };
}
