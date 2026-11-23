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
      explore: "Exploring",
      auditor: "Auditing",
      audit_review: "Reviewing",
    });
  });

  it("describes every role a researcher picks a model for", () => {
    expect(PICKABLE_ROLE_DESCRIPTIONS).toEqual({
      explore: "Talks a research question through before anything is built.",
      frame: "Turns your question into a plan of searches and fills in their settings.",
      lead: "Talks with you and decides what happens next.",
      verification: "Checks the built strategy and reports what it found.",
    });
    expect(phaseDescription("verification")).toBe(
      "Checks the built strategy and reports what it found.",
    );
  });

  it("offers no pick for the repair role, which runs on the deployment's tier", () => {
    expect(isPickableRole("execution")).toBe(false);
    expect(isPickableRole("lead")).toBe(true);
  });

  it("offers a pick for the explore role", () => {
    expect(isPickableRole("explore")).toBe(true);
    expect(phaseLabel("explore")).toBe("Exploring");
  });

  it("labels the audit roles and offers no pick for them", () => {
    expect(phaseLabel("auditor")).toBe("Auditing");
    expect(phaseLabel("audit_review")).toBe("Reviewing");
    expect(isPickableRole("auditor")).toBe(false);
    expect(isPickableRole("audit_review")).toBe(false);
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
