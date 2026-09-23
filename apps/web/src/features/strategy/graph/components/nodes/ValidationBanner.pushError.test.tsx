// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Step } from "@pathfinder/shared";
import { stepErrorMessage, ValidationBanner } from "./ValidationBanner";
import type { StepSnapshot } from "@/state/strategy/useStepSnapshot";

/**
 * The server keeps an edit WDK rejected and the rejection travels on the step.
 * The lifecycle machine does not change state, so the banner reads the step.
 */

function step(overrides: Partial<Step> = {}): Step {
  return {
    id: "s1",
    searchName: "GenesByTaxon",
    displayName: "Taxon",
    recordType: "transcript",
    parameters: {},
    primaryInputStepId: null,
    secondaryInputStepId: null,
    operator: null,
    isFiltered: false,
    status: "built",
    ...overrides,
  };
}

function snapshot(overrides: Partial<StepSnapshot> = {}): StepSnapshot {
  return {
    step: step(),
    lifecycleState: "idle",
    estimatedSize: null,
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

describe("ValidationBanner surfaces a WDK rejection", () => {
  it("shows the rejection even though the lifecycle is idle", () => {
    render(
      <ValidationBanner
        step={step()}
        snapshot={snapshot({ wdkPushError: "WDK rejected this step" })}
      />,
    );

    expect(screen.getByTestId("node-error-trigger").getAttribute("aria-label")).toBe(
      "WDK rejected this step",
    );
  });

  it("prefers the WDK reason over a generic validation message", () => {
    render(
      <ValidationBanner
        step={step()}
        snapshot={snapshot({
          isInvalid: true,
          wdkPushError: "organism is not a valid value",
          validationErrors: { general: ["Validation error"], byKey: {} },
        })}
      />,
    );

    expect(screen.getByTestId("node-error-trigger").getAttribute("aria-label")).toBe(
      "organism is not a valid value",
    );
  });

  it("stays silent for a healthy step", () => {
    render(<ValidationBanner step={step()} snapshot={snapshot()} />);

    expect(screen.queryByTestId("validation-message")).toBe(null);
  });
});

describe("stepErrorMessage", () => {
  it("is null for a healthy step", () => {
    expect(stepErrorMessage(snapshot())).toBe(null);
  });

  it("prefers the WDK rejection", () => {
    expect(
      stepErrorMessage(
        snapshot({
          isInvalid: true,
          wdkPushError: "wdk said no",
          validationErrors: { general: ["local"], byKey: {} },
          lastError: "transient",
        }),
      ),
    ).toBe("wdk said no");
  });

  it("falls to the validation error when WDK did not reject", () => {
    expect(
      stepErrorMessage(
        snapshot({
          isInvalid: true,
          validationErrors: { general: ["local"], byKey: {} },
          lastError: "transient",
        }),
      ),
    ).toBe("local");
  });

  it("falls to the transient error last", () => {
    expect(stepErrorMessage(snapshot({ isFailed: true, lastError: "boom" }))).toBe(
      "boom",
    );
  });

  it("never returns an empty message for a failed step", () => {
    expect(stepErrorMessage(snapshot({ isInvalid: true }))).toBe("Validation error");
  });
});
