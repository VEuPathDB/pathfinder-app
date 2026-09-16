"use client";

import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { CUSTOM_TIER } from "@/features/settings/tierPresets";

const TIER_LABELS: Record<string, string> = {
  quality: "Quality",
  balanced: "Balanced",
  default: "Default",
  fast: "Fast",
};

const TIER_HINTS: Record<string, string> = {
  quality: "Best models on the reasoning phases; slower and pricier.",
  balanced: "A mid-tier model for reasoning, cheaper for step building.",
  default: "One capable, inexpensive model everywhere.",
  fast: "Same model at low reasoning effort; quickest turnaround.",
};

interface TierPickerProps {
  presets: Record<string, TierPreset>;
  activeTier: string;
  onSelect: (tier: string) => void;
}

export function TierPicker({ presets, activeTier, onSelect }: TierPickerProps) {
  const tiers = Object.keys(presets);
  if (tiers.length === 0) return null;

  return (
    <div className="mb-4">
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-medium text-foreground">Preset</span>
        {activeTier === CUSTOM_TIER && (
          <span className="text-[10px] text-muted-foreground">
            Custom - phases below don&apos;t match a preset
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tiers.map((tier) => {
          const selected = tier === activeTier;
          return (
            <button
              key={tier}
              type="button"
              aria-pressed={selected}
              title={TIER_HINTS[tier] ?? ""}
              onClick={() => onSelect(tier)}
              className={
                selected
                  ? "rounded-md border border-primary bg-primary/10 px-2.5 py-1 text-xs font-medium text-foreground"
                  : "rounded-md border border-border/60 px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted/50"
              }
            >
              {TIER_LABELS[tier] ?? tier}
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        Presets fill in every phase below. Changing any phase switches this to Custom.
      </p>
    </div>
  );
}
