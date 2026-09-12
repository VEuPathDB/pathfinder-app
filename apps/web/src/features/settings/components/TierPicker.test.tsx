// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { CUSTOM_TIER } from "@/features/settings/tierPresets";
import { TierPicker } from "./TierPicker";

afterEach(cleanup);

const uniform = (modelId: string, effort: "low" | "medium" | "high"): TierPreset => ({
  roles: {
    lead: { modelId, reasoningEffort: effort },
    frame: { modelId, reasoningEffort: effort },
    execution: { modelId, reasoningEffort: effort },
    verification: { modelId, reasoningEffort: effort },
  },
});

const PRESETS: Record<string, TierPreset> = {
  quality: uniform("openai:gpt-5.6-sol", "high"),
  default: uniform("openai:gpt-5.6-luna", "medium"),
  fast: uniform("openai:gpt-5.6-luna", "low"),
};

describe("TierPicker", () => {
  it("renders a button per tier with readable labels", () => {
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={vi.fn()} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Quality",
      "Default",
      "Fast",
    ]);
  });

  it("marks only the active tier as pressed", () => {
    render(<TierPicker presets={PRESETS} activeTier="fast" onSelect={vi.fn()} />);
    expect(
      screen.getByRole("button", { name: "Fast" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "Quality" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("emits the tier key when a preset is clicked", () => {
    const onSelect = vi.fn();
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Quality" }));
    expect(onSelect).toHaveBeenCalledWith("quality");
  });

  it("explains the Custom state so the empty selection isn't confusing", () => {
    render(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={vi.fn()} />,
    );
    expect(screen.getByText(/don't match a preset/i)).toBeVisible();
    for (const tier of ["Quality", "Default", "Fast"]) {
      expect(
        screen.getByRole("button", { name: tier }).getAttribute("aria-pressed"),
      ).toBe("false");
    }
  });

  it("renders nothing while presets are still loading", () => {
    const { container } = render(
      <TierPicker presets={{}} activeTier={CUSTOM_TIER} onSelect={vi.fn()} />,
    );
    expect(container.textContent).toBe("");
  });

  it("falls back to the raw key for a tier it has no label for", () => {
    render(
      <TierPicker
        presets={{ experimental: uniform("openai:gpt-5.6-terra", "low") }}
        activeTier={CUSTOM_TIER}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "experimental" })).toHaveTextContent(
      "experimental",
    );
  });
});
