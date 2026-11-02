"use client";

import type { ReactElement } from "react";

import { ConsultCarousel } from "../content/parts/ConsultCarousel";
import { ProposalCardView } from "../content/parts/ProposalCard";
import { SeparationCardView } from "../content/parts/SeparationCard";
import { ToolApprovalCard } from "../content/parts/ToolApprovalControls";
import type { OpenCard } from "../content/parts/cardAnswers";
import { pendingConsultOf } from "../content/parts/consultData";
import type { ConsultDraft } from "../content/parts/consultDraft";
import {
  ADOPTION_TOOL_NAME,
  CONSULT_TOOL_NAME,
  PROPOSAL_TOOL_NAME,
} from "../rail/consultActions";
import { useChatHelpers } from "../runtime/chatHelpersContext";
import type { DockedCard } from "./useDockedCard";

function CardBody({
  card,
  draft,
  onDraft,
}: {
  card: OpenCard;
  draft: ConsultDraft;
  onDraft: (draft: ConsultDraft) => void;
}): ReactElement | null {
  const chat = useChatHelpers();
  switch (card.toolName) {
    case CONSULT_TOOL_NAME: {
      const pending = pendingConsultOf(card);
      if (pending.questions.length === 0) return null;
      return (
        <ConsultCarousel
          pending={pending}
          chat={chat}
          draft={draft}
          onDraft={onDraft}
        />
      );
    }
    case PROPOSAL_TOOL_NAME:
      return (
        <ProposalCardView messageId={card.messageId} toolCallId={card.toolCallId} />
      );
    case ADOPTION_TOOL_NAME:
      return (
        <SeparationCardView messageId={card.messageId} toolCallId={card.toolCallId} />
      );
    default:
      return <ToolApprovalCard toolCallId={card.toolCallId} />;
  }
}

export function DockedCardView({
  docked,
}: {
  docked: DockedCard;
}): ReactElement | null {
  if (docked.card === null) return null;
  return (
    <div
      data-testid="docked-card"
      className="max-h-[50vh] shrink-0 overflow-y-auto overscroll-contain"
    >
      <CardBody
        key={docked.card.approvalId}
        card={docked.card}
        draft={docked.draft}
        onDraft={docked.setDraft}
      />
    </div>
  );
}
