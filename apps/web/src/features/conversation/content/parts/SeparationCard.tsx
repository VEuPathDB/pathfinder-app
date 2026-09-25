"use client";

import { useAuiState } from "@assistant-ui/react";
import { Check, FlaskConical, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import { handleAdoptionAnswer } from "../../rail/consultActions";
import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { findAdoption } from "./separationCardData";

const DECISION_TEXT = {
  accepted: "You said yes.",
  declined: "You said no.",
} as const;

/** The card that offers a separation run's strategy. Its question is the
 * run's own, written from the counts the site returned. */
export function SeparationCard({ toolCallId }: { toolCallId: string }) {
  const currentId = useAuiState((s) => s.message.id);
  const chat = useChatHelpers();
  const [note, setNote] = useState("");
  const card = findAdoption(chat.messages, currentId, toolCallId);
  if (card === null) return null;
  return (
    <div
      data-testid="separation-card"
      className="space-y-2 rounded-lg border border-border bg-card/60 p-2"
    >
      <div className="flex items-start gap-2 px-1 text-sm font-medium">
        <FlaskConical
          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
          aria-hidden
        />
        <p data-testid="separation-question">{card.offer.question}</p>
      </div>
      {card.decision === "pending" ? (
        <>
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Why not? (optional, sent with a no)"
            rows={2}
            aria-label="Why not"
          />
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() =>
                handleAdoptionAnswer(chat, card.approvalId, { accepted: false, note })
              }
            >
              <X className="mr-1 size-4" aria-hidden /> No
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() =>
                handleAdoptionAnswer(chat, card.approvalId, { accepted: true, note })
              }
            >
              <Check className="mr-1 size-4" aria-hidden /> Yes
            </Button>
          </div>
        </>
      ) : (
        <p
          data-testid="separation-decision"
          className="px-1 text-xs text-muted-foreground"
        >
          {DECISION_TEXT[card.decision]}
        </p>
      )}
    </div>
  );
}
