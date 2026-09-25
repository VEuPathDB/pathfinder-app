// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Step } from "@pathfinder/shared";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";
import { STAGGER_DELAY_MS } from "@/features/strategy/graph/motion";

interface MotionDivProps extends ComponentProps<"div"> {
  initial?: unknown;
  animate?: unknown;
  transition?: unknown;
  exit?: unknown;
}

const motionDivCalls: MotionDivProps[] = [];

vi.mock("motion/react", async () => {
  const React = await import("react");
  return {
    motion: {
      div: ({
        initial: _initial,
        animate: _animate,
        transition: _transition,
        exit: _exit,
        children,
        ...rest
      }: MotionDivProps) => {
        motionDivCalls.push({
          initial: _initial,
          animate: _animate,
          transition: _transition,
          exit: _exit,
        });
        return React.createElement("div", rest, children);
      },
    },
  };
});

function setReducedMotion(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)" ? matches : false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => true,
  })) as typeof window.matchMedia;
}

import { NodeShell } from "./NodeShell";

function makeStep(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    kind: "search",
    displayName: "Genes by taxon",
    searchName: "GenesByTaxon",
    recordType: "gene",
    parameters: {},
    estimatedSize: 100,
    isFiltered: false,
    validation: null,
    ...overrides,
  };
}

function makeSnapshot(overrides: Partial<StepSnapshot> = {}): StepSnapshot {
  return {
    step: null,
    lifecycleState: "idle",
    estimatedSize: 100,
    validationErrors: null,
    lastError: null,
    isBusy: false,
    isInvalid: false,
    isFailed: false,
    isDraft: false,
    wdkPushError: null,
    ...overrides,
  };
}

function renderShell(overrides: Partial<ComponentProps<typeof NodeShell>> = {}) {
  const step = overrides.step ?? makeStep();
  return render(
    <NodeShell
      kind="search"
      step={step}
      selected={false}
      width={168}
      height={64}
      snapshot={makeSnapshot()}
      {...overrides}
    />,
  );
}

describe("NodeShell motion stagger", () => {
  beforeEach(() => {
    motionDivCalls.length = 0;
    setReducedMotion(false);
  });
  afterEach(() => cleanup());

  it("wraps the shell in a motion.div that applies fade-in-up enter animation", () => {
    renderShell({ enterDelayIndex: 0 });

    expect(motionDivCalls.length).toBeGreaterThan(0);
    const props = motionDivCalls[0]!;
    expect(props.initial).toEqual({ opacity: 0, y: 6 });
    expect(props.animate).toEqual({ opacity: 1, y: 0 });
    expect(props.transition).toEqual({
      delay: 0,
      duration: 0.2,
      ease: "easeOut",
    });
  });

  it("staggers the enter delay by index * STAGGER_DELAY_MS / 1000 seconds", () => {
    renderShell({ enterDelayIndex: 3 });

    const props = motionDivCalls[0]!;
    const expectedDelay = 3 * (STAGGER_DELAY_MS / 1000);
    expect(props.transition).toEqual({
      delay: expectedDelay,
      duration: 0.2,
      ease: "easeOut",
    });
  });

  it("treats a missing enterDelayIndex as 0", () => {
    renderShell({});

    const props = motionDivCalls[0]!;
    expect(props.transition).toEqual({
      delay: 0,
      duration: 0.2,
      ease: "easeOut",
    });
  });

  it("clamps a negative enterDelayIndex to 0", () => {
    renderShell({ enterDelayIndex: -1 });

    const props = motionDivCalls[0]!;
    expect(props.transition).toEqual({
      delay: 0,
      duration: 0.2,
      ease: "easeOut",
    });
  });

  it("respects prefers-reduced-motion: skips the transition and renders at final state", () => {
    setReducedMotion(true);
    renderShell({ enterDelayIndex: 5 });

    const props = motionDivCalls[0]!;
    // `initial: false` renders the node at its `animate` values.
    expect(props.initial).toBe(false);
    expect(props.animate).toEqual({ opacity: 1, y: 0 });
    expect(props.transition).toEqual({ duration: 0 });
  });

  it("preserves data-testid + data-kind + width/height on the wrapping element", () => {
    const step = makeStep({ id: "abc" });
    const { container } = renderShell({
      step,
      kind: "combine",
      width: 168,
      height: 112,
    });

    const wrapper = container.querySelector('[data-testid="rf-node-abc"]');
    expect(wrapper).not.toBeNull();
    expect(wrapper?.getAttribute("data-kind")).toBe("combine");
    expect((wrapper as HTMLElement | null)?.style.width).toBe("168px");
    expect((wrapper as HTMLElement | null)?.style.height).toBe("112px");
  });

  it("outlines an orphan step with the warning token", () => {
    const step = makeStep({ id: "orph" });
    const { container } = renderShell({ step, isOrphan: true });
    const surface = container.querySelector('[data-testid="rf-node-orph"] > div');
    expect(surface?.className).toContain("!border-warning/60");
    expect(surface?.className).not.toContain("amber");
  });

  it("exposes the enter-delay index via data-enter-delay-index for inspection", () => {
    const step = makeStep({ id: "n2" });
    const { container } = renderShell({ step, enterDelayIndex: 2 });
    const wrapper = container.querySelector('[data-testid="rf-node-n2"]');
    expect(wrapper?.getAttribute("data-enter-delay-index")).toBe("2");
  });
});

describe("NodeShell inline rename wiring", () => {
  afterEach(() => cleanup());

  it("commits the inline rename through onRename(stepId, trimmed name)", async () => {
    const user = userEvent.setup();
    const onRename = vi.fn();
    renderShell({ step: makeStep({ id: "leaf1", displayName: "Old name" }), onRename });

    await user.click(screen.getByText("Old name"));
    const input = screen.getByTestId("inline-rename-input");
    fireEvent.change(input, { target: { value: "  New name  " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onRename).toHaveBeenCalledWith("leaf1", "New name");
  });

  it("renders the name as a static titled label, not an editable trigger, when onRename is unwired", () => {
    renderShell({ step: makeStep({ id: "leaf2", displayName: "Static name" }) });
    const name = screen.getByText("Static name");
    expect(name.tagName).toBe("DIV");
    expect(name).toHaveAttribute("title", "Static name");
  });
});
