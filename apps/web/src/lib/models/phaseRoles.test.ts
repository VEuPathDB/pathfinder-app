import { describe, expect, it } from "vitest";
import {
  PHASE_DESCRIPTIONS,
  PHASE_LABELS,
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

  it("describes every role a preset can name", () => {
    expect(Object.keys(PHASE_DESCRIPTIONS).sort()).toEqual([
      "execution",
      "frame",
      "lead",
      "site_help",
      "verification",
    ]);
    for (const text of Object.values(PHASE_DESCRIPTIONS)) {
      expect(text.length).toBeGreaterThan(0);
    }
  });

  it("falls back to the role name, and to no description", () => {
    expect(phaseLabel("curation")).toBe("curation");
    expect(phaseDescription("curation")).toBe("");
  });

  it("names no internal word in a label or a description", () => {
    for (const text of [
      ...Object.values(PHASE_LABELS),
      ...Object.values(PHASE_DESCRIPTIONS),
    ]) {
      expect(INTERNAL.test(text), text).toBe(false);
    }
  });
});
