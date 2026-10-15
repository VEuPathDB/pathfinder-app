"use client";

import type { ReasoningEffort } from "@pathfinder/shared";
import { Slider } from "@/components/ui/slider";

const EFFORTS: { value: ReasoningEffort; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "Extra high" },
  { value: "max", label: "Max" },
];

interface ReasoningSliderProps {
  value: ReasoningEffort;
  onChange: (effort: ReasoningEffort) => void;
}

export function ReasoningSlider({ value, onChange }: ReasoningSliderProps) {
  const index = Math.max(
    0,
    EFFORTS.findIndex((effort) => effort.value === value),
  );
  const label = EFFORTS[index]?.label ?? "";
  return (
    <div className="flex items-center gap-3">
      <Slider
        min={0}
        max={EFFORTS.length - 1}
        step={1}
        value={[index]}
        onValueChange={([next]) => {
          const picked = EFFORTS[next ?? index];
          if (picked !== undefined && picked.value !== value) onChange(picked.value);
        }}
        thumbLabel="Reasoning effort"
        valueText={label}
        className="w-28"
      />
      <span className="w-16 text-xs text-muted-foreground tabular-nums">{label}</span>
    </div>
  );
}
