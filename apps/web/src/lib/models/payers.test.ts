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
import {
  ANTHROPIC_FLAGSHIP,
  ANTHROPIC_SMALL,
  DEFAULT_MODEL,
} from "@/lib/models/__fixtures__/models";

function entry(
  id: string,
  enabled: boolean,
  deploymentMayPay = true,
): ModelCatalogEntry {
  const [provider = "", modelName = ""] = id.split(":");
  return {
    id,
    name: modelName,
    modelName,
    rank: "standard",
    provider: provider as ModelCatalogEntry["provider"],
    deploymentMayPay,
    enabled,
  };
}

const ANTHROPIC = entry(ANTHROPIC_SMALL.id, false);
const OPUS = entry(ANTHROPIC_FLAGSHIP.id, false, false);
const OPENAI = entry(DEFAULT_MODEL.id, true);
const DEPLOYMENT_ONLY: Payers = { openai: "deployment" };
const USER_ONLY: Payers = { anthropic: "user" };
const MIXED: Payers = { openai: "deployment", anthropic: "user" };
const ROLES = ["lead", "frame", "execution", "verification"];
const DEFAULTS = {
  lead: DEFAULT_MODEL.id,
  frame: DEFAULT_MODEL.id,
  execution: DEFAULT_MODEL.id,
  verification: DEFAULT_MODEL.id,
};

describe("selectable", () => {
  it("reads the deployment's view while the reader's payers are unknown", () => {
    expect([selectable(ANTHROPIC, undefined), selectable(OPENAI, undefined)]).toEqual([
      false,
      true,
    ]);
  });

  it("offers a provider the researcher's own key pays for", () => {
    expect([selectable(ANTHROPIC, USER_ONLY), selectable(OPENAI, USER_ONLY)]).toEqual([
      true,
      false,
    ]);
  });

  it("offers every provider someone pays for", () => {
    expect([selectable(ANTHROPIC, MIXED), selectable(OPENAI, MIXED)]).toEqual([
      true,
      true,
    ]);
  });

  it("offers a model only a researcher's key runs on that key alone", () => {
    expect([
      selectable(OPUS, { anthropic: "user" }),
      selectable(OPUS, { anthropic: "deployment" }),
      selectable(ANTHROPIC, { anthropic: "deployment" }),
    ]).toEqual([true, false, true]);
  });

  it("marks a model that runs on the researcher's key", () => {
    expect([onOwnKey(ANTHROPIC, MIXED), onOwnKey(OPENAI, MIXED)]).toEqual([
      true,
      false,
    ]);
  });

  it("rewrites enabled from the payers", () => {
    expect(withPayers([ANTHROPIC, OPENAI], USER_ONLY).map((m) => m.enabled)).toEqual([
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
      lead: ANTHROPIC_SMALL.id,
      frame: ANTHROPIC_SMALL.id,
      execution: ANTHROPIC_SMALL.id,
      verification: ANTHROPIC_SMALL.id,
    };
    expect(rolesPaidByDeployment(ROLES, picks, DEFAULTS, USER_ONLY)).toEqual([]);
  });

  it("names the roles left on the deployment in a mixed turn", () => {
    const picks = { lead: ANTHROPIC_SMALL.id };
    expect(rolesPaidByDeployment(ROLES, picks, DEFAULTS, MIXED)).toEqual([
      "frame",
      "execution",
      "verification",
    ]);
  });
});

describe("refusedProvidersInUse", () => {
  it("names a refused provider only when a role runs on it", () => {
    const picks = { lead: ANTHROPIC_SMALL.id };
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
