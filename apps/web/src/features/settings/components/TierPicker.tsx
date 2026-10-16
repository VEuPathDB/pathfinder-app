"use client";

import { useState } from "react";

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
  const [lastPreset, setLastPreset] = useState("default");
  const tiers = Object.keys(presets).sort((a, b) => rank(a) - rank(b));
  const active = tiers.indexOf(activeTier);
  if (active !== -1 && activeTier !== lastPreset) setLastPreset(activeTier);
  if (tiers.length === 0) return null;
  const custom = active === -1;
  const thumb = custom ? Math.max(tiers.indexOf(lastPreset), 0) : active;
  const label = (tier: string) => TIER_LABELS[tier] ?? tier;
  const pickUnderThumb = () => {
    const tier = tiers[thumb];
    if (custom && tier !== undefined) onSelect(tier);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-foreground">Preset</span>
        <span className="text-xs text-muted-foreground">
          {custom ? "Custom" : (TIER_HINTS[activeTier] ?? "")}
        </span>
      </div>
      <Slider
        min={0}
        max={Math.max(tiers.length - 1, 1)}
        step={1}
        value={[thumb]}
        onValueChange={([next]) => {
          const tier = next === undefined ? undefined : tiers[next];
          if (tier !== undefined && tier !== activeTier) onSelect(tier);
        }}
        onPointerDown={pickUnderThumb}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          pickUnderThumb();
        }}
        thumbLabel="Preset"
        valueText={custom ? "Custom" : label(activeTier)}
        data-custom={custom || undefined}
        className="data-[custom]:[&_[data-slot=slider-range]]:bg-muted-foreground/35 data-[custom]:[&_[data-slot=slider-thumb]]:border-muted-foreground/50"
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
