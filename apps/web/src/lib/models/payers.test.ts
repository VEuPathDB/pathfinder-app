import { describe, expect, it } from "vitest";
import type { ModelCatalogEntry } from "@pathfinder/shared";

import {
  assistantRoles,
  onOwnKey,
  refusedProvidersInUse,
  rolesPaidByDeployment,
  selectable,
  withPayers,
  type Payers,
} from "./payers";

function entry(id: string, enabled: boolean): ModelCatalogEntry {
  const [provider = "", modelName = ""] = id.split(":");
  return {
    id,
    name: modelName,
    modelName,
    provider: provider as ModelCatalogEntry["provider"],
    enabled,
  };
}

const OPUS = entry("anthropic:claude-opus-5", false);
const LUNA = entry("openai:gpt-5.6-luna", true);
const DEPLOYMENT_ONLY: Payers = { openai: "deployment" };
const USER_ONLY: Payers = { anthropic: "user" };
const MIXED: Payers = { openai: "deployment", anthropic: "user" };
const ROLES = ["lead", "frame", "execution", "verification"];
const DEFAULTS = {
  lead: "openai:gpt-5.6-luna",
  frame: "openai:gpt-5.6-luna",
  execution: "openai:gpt-5.6-luna",
  verification: "openai:gpt-5.6-luna",
};

describe("selectable", () => {
  it("reads the deployment's view while the reader's payers are unknown", () => {
    expect([selectable(OPUS, undefined), selectable(LUNA, undefined)]).toEqual([
      false,
      true,
    ]);
  });

  it("offers a provider the researcher's own key pays for", () => {
    expect([selectable(OPUS, USER_ONLY), selectable(LUNA, USER_ONLY)]).toEqual([
      true,
      false,
    ]);
  });

  it("offers every provider someone pays for", () => {
    expect([selectable(OPUS, MIXED), selectable(LUNA, MIXED)]).toEqual([true, true]);
  });

  it("marks a model that runs on the researcher's key", () => {
    expect([onOwnKey(OPUS, MIXED), onOwnKey(LUNA, MIXED)]).toEqual([true, false]);
  });

  it("rewrites enabled from the payers", () => {
    expect(withPayers([OPUS, LUNA], USER_ONLY).map((m) => m.enabled)).toEqual([
      true,
      false,
    ]);
  });
});

describe("rolesPaidByDeployment", () => {
  it("names every role the deployment pays for", () => {
    expect(rolesPaidByDeployment(ROLES, {}, DEFAULTS, DEPLOYMENT_ONLY)).toEqual(ROLES);
  });

  it("names none when every role runs on the researcher's keys", () => {
    const picks = {
      lead: "anthropic:claude-opus-5",
      frame: "anthropic:claude-opus-5",
      execution: "anthropic:claude-sonnet-5",
      verification: "anthropic:claude-opus-5",
    };
    expect(rolesPaidByDeployment(ROLES, picks, DEFAULTS, USER_ONLY)).toEqual([]);
  });

  it("names the roles left on the deployment in a mixed turn", () => {
    const picks = { lead: "anthropic:claude-opus-5" };
    expect(rolesPaidByDeployment(ROLES, picks, DEFAULTS, MIXED)).toEqual([
      "frame",
      "execution",
      "verification",
    ]);
  });
});

describe("refusedProvidersInUse", () => {
  it("names a refused provider only when a role runs on it", () => {
    const picks = { lead: "anthropic:claude-opus-5" };
    expect(refusedProvidersInUse(ROLES, picks, DEFAULTS, ["anthropic"])).toEqual([
      "anthropic",
    ]);
    expect(refusedProvidersInUse(ROLES, {}, DEFAULTS, ["anthropic"])).toEqual([]);
  });
});

describe("assistantRoles", () => {
  it("lists the roles an assistant's presets name, once each", () => {
    const presets = {
      pathfinder: {
        openai: {
          default: { roles: { lead: {}, frame: {} } },
          fast: { roles: { lead: {}, frame: {} } },
        },
      },
      site_help: { openai: { default: { roles: { site_help: {} } } } },
    };
    expect(assistantRoles(presets, "pathfinder")).toEqual(["lead", "frame"]);
    expect(assistantRoles(presets, "site_help")).toEqual(["site_help"]);
    expect(assistantRoles(undefined, "pathfinder")).toEqual([]);
  });
});
