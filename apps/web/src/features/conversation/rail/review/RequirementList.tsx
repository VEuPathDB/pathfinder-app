"use client";

import { Check, CircleDashed, Minus, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils/cn";

import {
  REQUIREMENT_WORDS,
  type RequirementRow,
  type RequirementStatus,
} from "./reviewModel";

const MARK: Record<RequirementStatus, { icon: LucideIcon; tone: string }> = {
  met: { icon: Check, tone: "text-success" },
  different: { icon: Minus, tone: "text-warning" },
  missed: { icon: X, tone: "text-destructive" },
  unchecked: { icon: CircleDashed, tone: "text-muted-foreground" },
};

export function RequirementList({ rows }: { rows: readonly RequirementRow[] }) {
  if (rows.length === 0) return null;
  return (
    <ul className="flex flex-col">
      {rows.map((row) => {
        const { icon: Icon, tone } = MARK[row.status];
        return (
          <li
            key={row.key}
            className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-2.5 border-t border-dashed border-border py-2 first:border-t-0"
          >
            <Icon
              role="img"
              className={cn("mt-0.5 size-4", tone)}
              aria-label={REQUIREMENT_WORDS[row.status]}
            />
            <div className="min-w-0">
              <p className="text-sm text-foreground">{row.label}</p>
              <p className="text-xs text-muted-foreground">
                {row.requested}
                {row.status !== "met" && ` · ${REQUIREMENT_WORDS[row.status]}`}
              </p>
              {row.note !== null && (
                <p className="text-xs text-muted-foreground">{row.note}</p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
