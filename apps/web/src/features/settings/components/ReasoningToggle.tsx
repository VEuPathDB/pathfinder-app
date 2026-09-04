"use client";

import type { ReasoningEffort } from "@pathfinder/shared";
import { cn } from "@/lib/utils/cn";

const OPTIONS: { value: ReasoningEffort; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

interface ReasoningToggleProps {
  value: ReasoningEffort;
  onChange: (effort: ReasoningEffort) => void;
  disabled?: boolean;
}

export function ReasoningToggle({ value, onChange, disabled }: ReasoningToggleProps) {
  return (
    <div
      className="inline-flex items-center rounded-md border border-input bg-background text-xs"
      role="radiogroup"
      aria-label="Reasoning effort"
    >
      {OPTIONS.map((opt) => {
        const isActive = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              "px-2.5 py-1 font-medium transition-all duration-150 first:rounded-l-[5px] last:rounded-r-[5px]",
              isActive
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              "disabled:cursor-not-allowed disabled:opacity-50",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
