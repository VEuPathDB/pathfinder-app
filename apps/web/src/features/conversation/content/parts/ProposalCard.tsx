"use client";

import { useAuiState } from "@assistant-ui/react";
import { Check, Lightbulb, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { handleProposalAnswer } from "../../rail/consultActions";
import { useChatHelpers, type ChatHelpers } from "../../runtime/chatHelpersContext";
import { findProposal, type ProposalCardData } from "./consultData";

export function ProposalCard({ toolCallId }: { toolCallId: string }) {
  const currentId = useAuiState((s) => s.message.id);
  const chat = useChatHelpers();
  const message = chat.messages.find((m) => m.id === currentId);
  if (message?.role !== "assistant") return null;
  const card = findProposal(message, toolCallId);
  if (card === null) return null;
  return <ProposalCardView card={card} chat={chat} />;
}

const DECISION_TEXT = {
  accepted: "You said yes.",
  declined: "You said no.",
} as const;

function ProposalCardView({
  card,
  chat,
}: {
  card: ProposalCardData;
  chat: ChatHelpers;
}) {
  const [note, setNote] = useState("");
  const { proposal } = card;

  return (
    <div
      data-testid="proposal-card"
      className="space-y-2 rounded-lg border border-border bg-card/60 p-2"
    >
      <div className="flex items-start gap-2 px-1 text-sm font-medium">
        <Lightbulb
          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
          aria-hidden
        />
        <p data-testid="proposal-question">{proposal.question}</p>
      </div>
      <ul
        aria-label="Proposed changes"
        className="list-disc space-y-1 rounded-md border border-border bg-background/60 py-2.5 pl-7 pr-2.5 text-xs leading-snug text-foreground"
      >
        {proposal.proposedChanges.map((change, index) => (
          <li key={index}>{change}</li>
        ))}
      </ul>
      {card.decision === "pending" ? (
        <ProposalAnswer
          onAnswer={(accepted) =>
            handleProposalAnswer(
              chat,
              { approvalId: card.approvalId, question: proposal.question },
              { accepted, note },
            )
          }
          note={note}
          onNote={setNote}
        />
      ) : (
        <p
          data-testid="proposal-decision"
          className="px-1 text-xs text-muted-foreground"
        >
          {DECISION_TEXT[card.decision]}
        </p>
      )}
    </div>
  );
}

function ProposalAnswer({
  onAnswer,
  note,
  onNote,
}: {
  onAnswer: (accepted: boolean) => void;
  note: string;
  onNote: (note: string) => void;
}) {
  return (
    <>
      <Textarea
        value={note}
        onChange={(e) => onNote(e.target.value)}
        placeholder="Add a note (optional)..."
        rows={2}
        aria-label="Add a note"
        data-testid="proposal-note"
      />
      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => onAnswer(false)}
          data-testid="proposal-no"
        >
          <X className="mr-1 size-4" aria-hidden /> No
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() => onAnswer(true)}
          data-testid="proposal-yes"
        >
          <Check className="mr-1 size-4" aria-hidden /> Yes
        </Button>
      </div>
    </>
  );
}
