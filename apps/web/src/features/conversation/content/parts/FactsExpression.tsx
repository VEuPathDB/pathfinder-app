"use client";

import { Check, Copy } from "lucide-react";
import { useState, type ReactElement } from "react";

import { Button } from "@/components/ui/button";

export function FactsExpression({ expression }: { expression: string }): ReactElement {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(expression);
    setCopied(true);
  };
  const Icon = copied ? Check : Copy;
  return (
    <div className="mt-1 flex items-start gap-1">
      <pre
        data-testid="facts-param-expression"
        className="min-w-0 flex-1 select-all whitespace-pre-wrap break-all rounded border border-border bg-muted/40 px-2 py-1 font-mono text-[11px] text-foreground"
      >
        {expression}
      </pre>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label="Copy the expression"
        className="size-6 shrink-0"
        onClick={() => void copy()}
      >
        <Icon className="size-3" aria-hidden />
      </Button>
    </div>
  );
}
