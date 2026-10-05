import { describe, expect, it } from "vitest";
import {
  PHASE_LABELS,
  PICKABLE_ROLE_DESCRIPTIONS,
  isPickableRole,
  phaseDescription,
  phaseLabel,
} from "./phaseRoles";

const INTERNAL = /\b(EDA|WDK|FRAME|BUILD|VERIFY|Frame|Ledger|Lead|sub-agent)\b/;

describe("phase role metadata", () => {
  it("labels every phase the wire carries, including the recorded alias", () => {
    expect(PHASE_LABELS).toEqual({
      lead: "Assistant",
      frame: "Planning",
      build: "Building",
      execution: "Building",
      verification: "Checking",
      recover_failed_steps: "Repairing",
      site_help: "Site help",
    });
  });

  it("describes every role a researcher picks a model for", () => {
    expect(Object.keys(PICKABLE_ROLE_DESCRIPTIONS).sort()).toEqual([
      "frame",
      "lead",
      "site_help",
      "verification",
    ]);
    for (const text of Object.values(PICKABLE_ROLE_DESCRIPTIONS)) {
      expect(text.length).toBeGreaterThan(0);
    }
    expect(phaseDescription("verification")).toBe(
      "Checks the built strategy and reports what it found.",
    );
  });

  it("offers no pick for the repair role, which runs on the deployment's tier", () => {
    expect(isPickableRole("execution")).toBe(false);
    expect(isPickableRole("lead")).toBe(true);
    expect(isPickableRole("site_help")).toBe(true);
  });

  it("falls back to the role name for a label", () => {
    expect(phaseLabel("curation")).toBe("curation");
  });

  it("names no internal word in a label or a description", () => {
    for (const text of [
      ...Object.values(PHASE_LABELS),
      ...Object.values(PICKABLE_ROLE_DESCRIPTIONS),
    ]) {
      expect(INTERNAL.test(text), text).toBe(false);
    }
  });
});
