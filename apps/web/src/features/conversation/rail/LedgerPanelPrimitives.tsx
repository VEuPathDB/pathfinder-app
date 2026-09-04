"use client";

import { Check, X } from "lucide-react";
import type { ReactNode } from "react";

import { type Tone, toneBadge } from "@/features/conversation/rail/statusTone";

export function LedgerSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="px-4 py-3">
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-1.5">{children}</div>
    </section>
  );
}

export function LedgerRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1">{value}</div>
    </div>
  );
}

export function BoolBadge({ value }: { value: boolean }) {
  return value ? (
    <span className="inline-flex items-center gap-1 rounded bg-success/15 px-1.5 py-0.5 text-[10px] font-medium text-success">
      <Check className="h-3 w-3" /> yes
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
      <X className="h-3 w-3" /> no
    </span>
  );
}

export function CountChip({ value, tone = "neutral" }: { value: number; tone?: Tone }) {
  return (
    <span
      className={`inline-flex min-w-[1.5rem] justify-center rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${toneBadge(tone)}`}
    >
      {value}
    </span>
  );
}

export function StatusPill({
  text,
  tone = "neutral",
}: {
  text: string | undefined;
  tone?: Tone;
}) {
  if (text === undefined) return null;
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${toneBadge(tone)}`}
    >
      {text}
    </span>
  );
}
