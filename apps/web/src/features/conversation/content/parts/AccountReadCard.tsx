"use client";

import { ShieldAlert } from "lucide-react";
import { useId, useState, type ReactElement } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { allowInThisConversation, setAlwaysAllowed } from "@/lib/api/accountReads";

export const ACCOUNT_READ_TOOL = "ask_to_read_the_account";

const askedInput = z.object({ what: z.string() });

export function accountReadWhat(input: unknown): string {
  return askedInput.safeParse(input).data?.what ?? "";
}

function AllowanceBox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}): ReactElement {
  const id = useId();
  return (
    <div className="flex items-center gap-2 text-xs">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(next) => onChange(next === true)}
      />
      <label htmlFor={id}>{label}</label>
    </div>
  );
}

export function AccountReadCard({
  conversationId,
  what,
  onAnswer,
}: {
  conversationId: string;
  what: string;
  onAnswer: (allowed: boolean) => void;
}): ReactElement {
  const [thisConversation, setThisConversation] = useState(false);
  const [everyConversation, setEveryConversation] = useState(false);
  const [sending, setSending] = useState(false);

  const allow = async () => {
    setSending(true);
    if (thisConversation) await allowInThisConversation(conversationId);
    if (everyConversation) await setAlwaysAllowed(true);
    onAnswer(true);
  };

  return (
    <div
      data-testid="account-read-card"
      className="mt-3 space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3"
    >
      <p className="flex items-center gap-1.5 text-xs font-medium">
        <ShieldAlert className="size-3.5 text-warning" aria-hidden />
        Let PathFinder read your strategies, other conversations or gene sets?
      </p>
      <p data-testid="account-read-what" className="text-xs text-muted-foreground">
        {what}
      </p>
      <AllowanceBox
        label="Always allow in this conversation"
        checked={thisConversation}
        onChange={setThisConversation}
      />
      <AllowanceBox
        label="Always allow in all conversations"
        checked={everyConversation}
        onChange={setEveryConversation}
      />
      <div className="flex gap-2">
        <Button size="sm" disabled={sending} onClick={() => void allow()}>
          Allow
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={sending}
          onClick={() => onAnswer(false)}
        >
          Don&apos;t allow
        </Button>
      </div>
    </div>
  );
}
