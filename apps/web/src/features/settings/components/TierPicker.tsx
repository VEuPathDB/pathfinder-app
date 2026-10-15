"use client";

import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils/cn";

const TIER_ORDER = ["fast", "default", "balanced", "quality"];

const TIER_LABELS: Record<string, string> = {
  quality: "Quality",
  balanced: "Balanced",
  default: "Default",
  fast: "Fast",
};

const TIER_HINTS: Record<string, string> = {
  quality: "Best models on the reasoning phases; slower and pricier.",
  balanced: "A mid-tier model for planning, a cheaper one for checking.",
  default: "One capable, inexpensive model everywhere.",
  fast: "Same model at low reasoning effort; quickest turnaround.",
};

function rank(tier: string): number {
  const at = TIER_ORDER.indexOf(tier);
  return at === -1 ? TIER_ORDER.length : at;
}

interface TierPickerProps {
  presets: Record<string, TierPreset>;
  activeTier: string;
  onSelect: (tier: string) => void;
}

export function TierPicker({ presets, activeTier, onSelect }: TierPickerProps) {
  const tiers = Object.keys(presets).sort((a, b) => rank(a) - rank(b));
  if (tiers.length === 0) return null;
  const active = tiers.indexOf(activeTier);
  const label = (tier: string) => TIER_LABELS[tier] ?? tier;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-foreground">Preset</span>
        <span className="text-xs text-muted-foreground">
          {active === -1 ? "Custom" : (TIER_HINTS[activeTier] ?? "")}
        </span>
      </div>
      <Slider
        min={0}
        max={Math.max(tiers.length - 1, 1)}
        step={1}
        value={active === -1 ? [] : [active]}
        onValueChange={([next]) => {
          const tier = next === undefined ? undefined : tiers[next];
          if (tier !== undefined && tier !== activeTier) onSelect(tier);
        }}
        thumbLabel="Preset"
        valueText={active === -1 ? "Custom" : label(activeTier)}
      />
      <div className="flex justify-between">
        {tiers.map((tier) => {
          const selected = tier === activeTier;
          return (
            <button
              key={tier}
              type="button"
              aria-pressed={selected}
              title={TIER_HINTS[tier] ?? ""}
              onClick={() => onSelect(tier)}
              className={cn(
                "rounded px-1 text-xs transition-colors",
                selected
                  ? "font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {label(tier)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
