// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { TierPreset } from "@pathfinder/shared/generated/types/TierPreset";
import { CUSTOM_TIER } from "@/features/settings/tierPresets";
import { TierPicker } from "./TierPicker";
import {
  DEFAULT_MODEL,
  OPENAI_FLAGSHIP,
  OPENAI_SMALL,
} from "@/lib/models/__fixtures__/models";

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
  quality: uniform(OPENAI_FLAGSHIP.id, "high"),
  default: uniform(DEFAULT_MODEL.id, "medium"),
  fast: uniform(DEFAULT_MODEL.id, "low"),
};

describe("TierPicker", () => {
  it("lays the tiers out from fastest to best, each a stop on the slider", () => {
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={vi.fn()} />);

    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Fast",
      "Default",
      "Quality",
    ]);
    const slider = screen.getByRole("slider", { name: "Preset" });
    expect(slider).toHaveAttribute("aria-valuemax", "2");
    expect(slider).toHaveAttribute("aria-valuenow", "1");
    expect(slider).toHaveAttribute("aria-valuetext", "Default");
  });

  it("centers each tier's name where the slider centers its thumb", () => {
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={vi.fn()} />);
    expect(
      ["Fast", "Default", "Quality"].map(
        (name) => screen.getByRole("button", { name }).style.left,
      ),
    ).toEqual(["calc(0% + 8px)", "calc(50% + 0px)", "calc(100% - 8px)"]);
  });

  it("marks only the active tier as pressed", () => {
    render(<TierPicker presets={PRESETS} activeTier="fast" onSelect={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Fast" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Quality" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("emits the tier key when a tier's name is clicked", () => {
    const onSelect = vi.fn();
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Quality" }));
    expect(onSelect).toHaveBeenCalledWith("quality");
  });

  it("emits the next tier when the slider moves", () => {
    const onSelect = vi.fn();
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Preset" }), {
      key: "ArrowRight",
    });
    expect(onSelect).toHaveBeenCalledWith("quality");
  });

  it("names the Custom state, greys the slider and presses no tier", () => {
    render(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={vi.fn()} />,
    );
    expect(screen.getByText("Custom")).toBeVisible();
    const slider = screen.getByRole("slider", { name: "Preset" });
    expect(slider).toHaveAttribute("aria-valuetext", "Custom");
    expect(slider.closest('[data-slot="slider"]')).toHaveAttribute("data-custom");
    for (const tier of ["Quality", "Default", "Fast"]) {
      expect(screen.getByRole("button", { name: tier })).toHaveAttribute(
        "aria-pressed",
        "false",
      );
    }
  });

  it("keeps the thumb on the last preset when the stages go custom", () => {
    const { rerender } = render(
      <TierPicker presets={PRESETS} activeTier="fast" onSelect={vi.fn()} />,
    );
    rerender(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={vi.fn()} />,
    );
    expect(screen.getByRole("slider", { name: "Preset" })).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
  });

  it("starts a custom picker on the default preset", () => {
    render(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={vi.fn()} />,
    );
    expect(screen.getByRole("slider", { name: "Preset" })).toHaveAttribute(
      "aria-valuenow",
      "1",
    );
  });

  it("picks the preset the thumb moves to from Custom", () => {
    const onSelect = vi.fn();
    render(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={onSelect} />,
    );
    fireEvent.keyDown(screen.getByRole("slider", { name: "Preset" }), {
      key: "ArrowLeft",
    });
    expect(onSelect).toHaveBeenCalledWith("fast");
  });

  it("picks the preset under the thumb when it is pressed in Custom", () => {
    Object.defineProperty(Element.prototype, "setPointerCapture", {
      configurable: true,
      value: vi.fn(),
    });
    const onSelect = vi.fn();
    render(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={onSelect} />,
    );
    try {
      fireEvent.pointerDown(screen.getByRole("slider", { name: "Preset" }));
      expect(onSelect).toHaveBeenCalledWith("default");
    } finally {
      Reflect.deleteProperty(Element.prototype, "setPointerCapture");
    }
  });

  it.each(["Enter", " "])("picks the preset under the thumb on %j in Custom", (key) => {
    const onSelect = vi.fn();
    render(
      <TierPicker presets={PRESETS} activeTier={CUSTOM_TIER} onSelect={onSelect} />,
    );
    fireEvent.keyDown(screen.getByRole("slider", { name: "Preset" }), { key });
    expect(onSelect).toHaveBeenCalledWith("default");
  });

  it("does nothing when the thumb of an active preset is pressed", () => {
    const onSelect = vi.fn();
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={onSelect} />);
    fireEvent.keyDown(screen.getByRole("slider", { name: "Preset" }), {
      key: "Enter",
    });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("does not mark a preset as custom", () => {
    render(<TierPicker presets={PRESETS} activeTier="default" onSelect={vi.fn()} />);
    expect(
      screen.getByRole("slider", { name: "Preset" }).closest('[data-slot="slider"]'),
    ).not.toHaveAttribute("data-custom");
  });

  it("renders nothing while presets are still loading", () => {
    const { container } = render(
      <TierPicker presets={{}} activeTier={CUSTOM_TIER} onSelect={vi.fn()} />,
    );
    expect(container.textContent).toBe("");
  });

  it("hints at what a tier fills in", () => {
    render(
      <TierPicker
        presets={{ balanced: uniform(DEFAULT_MODEL.id, "medium") }}
        activeTier="balanced"
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Balanced" })).toHaveAttribute(
      "title",
      "A mid-tier model for planning, a cheaper one for checking.",
    );
  });

  it("places a tier it has no label for after the known ones, by its raw key", () => {
    render(
      <TierPicker
        presets={{ experimental: uniform(OPENAI_SMALL.id, "low"), ...PRESETS }}
        activeTier={CUSTOM_TIER}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Fast",
      "Default",
      "Quality",
      "experimental",
    ]);
  });
});
