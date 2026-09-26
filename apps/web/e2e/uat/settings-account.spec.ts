/**
 * UAT flows A1 to A7: the Settings tabs, the usage figures of a turn, the data
 * tab, privacy, the local settings and seeding. Prices, counts and model names
 * are read from the api at run time; only the model is mocked.
 */

import type { Locator, Page } from "@playwright/test";
import { siteShortName, type GeneSet } from "@pathfinder/shared";
import type { ModelListResponse } from "@pathfinder/shared/generated/types/ModelListResponse";
import type { PurgeUserDataResponse } from "@pathfinder/shared/generated/types/PurgeUserDataResponse";
import type { QuotaResponse } from "@pathfinder/shared/generated/types/QuotaResponse";
import type { TierListResponse } from "@pathfinder/shared/generated/types/TierListResponse";

import {
  formatCost,
  formatTokens,
  formatUsage,
} from "@/features/conversation/usageFormat";
import { formatCompactClean, formatPrice } from "@/features/settings/format";
import { presetsForProvider, rolesForAssistant } from "@/features/settings/tierPresets";
import { DEFAULT_ASSISTANT_ID, assistantLabel } from "@/lib/assistants";
import { readsLabel } from "@/lib/models/attachments";
import { phaseLabel } from "@/lib/models/phaseRoles";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import {
  type ApiClient,
  type ConversationRow,
  fetchLastTurnUsage,
  listBody,
  listConversations,
} from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild, openTrace } from "../fixtures/build-checks";
import { countPattern, siteControlSets, siteOrganism } from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";
import type { SettingsPage } from "../pages/settings.page";

const S1_TEXT = (organism: string) =>
  `Find ${organism} genes whose proteins have a predicted signal peptide.`;
const COUNT_QUESTION = "How many genes does this strategy return?";

const TAB_LABELS = [
  "Model",
  "Provider keys",
  "Data",
  "Memory",
  "Privacy",
  "Advanced",
  "Seeding",
];
const TIER_LABELS: Record<string, string> = {
  quality: "Quality",
  balanced: "Balanced",
  default: "Default",
  fast: "Fast",
};

/** The quota pill prints the limit with two decimals. */
const limitFormat = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function settingsDialog(page: Page): Locator {
  return page.getByRole("dialog", { name: "Settings", exact: true });
}

/** The one open tooltip that carries `text`. */
function tooltip(page: Page, text: string): Locator {
  return page.locator('[data-slot="tooltip-content"]').filter({ hasText: text });
}

function normalize(text: string | null): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

/** Open the site's conversation route without creating a conversation. */
async function openSite(page: Page, siteId: string) {
  await page.goto(`/${siteId}/conversation`);
  await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });
}

/** Open Settings on the tab labelled `label`. */
async function openSettingsTab(page: Page, settingsPage: SettingsPage, label: string) {
  await settingsPage.open();
  const tab = settingsDialog(page).getByRole("tab", { name: label, exact: true });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

async function readJson<T>(api: ApiClient, path: string): Promise<T> {
  const resp = await api.get(path);
  expect(resp.status(), `${path} ${await resp.text()}`).toBe(200);
  return (await resp.json()) as T;
}

/** Build one arc on a fresh conversation of the project's site. */
async function buildOn(
  chatPage: ChatPage,
  siteId: string,
  message: string,
): Promise<string> {
  await chatPage.startOn(siteId);
  await chatPage.sendAndSettle(message);
  const id = chatPage.lastStrategyId;
  if (id === null) throw new Error("the conversation has no id");
  return id;
}

/** The trace header reads "<model> - <tokens>, <cost>". */
function chipUsage(text: string): string {
  const match = /^.+ - (?<usage>[^,]+, \S+)$/.exec(text);
  if (match?.groups === undefined) {
    throw new Error(`the trace header does not read as a usage line: "${text}"`);
  }
  return match.groups["usage"] ?? "";
}

/** The deletion the Data tab asks the api for, with what the api answered. */
function purgeResponse(page: Page) {
  return page.waitForResponse(
    (r) => r.url().includes("/api/v1/user/data") && r.request().method() === "DELETE",
    { timeout: 240_000 },
  );
}

async function geneSetsOn(api: ApiClient, siteId?: string): Promise<GeneSet[]> {
  const query = siteId === undefined ? "" : `?siteId=${siteId}`;
  return listBody(await api.get(`/api/v1/gene-sets${query}`), "gene sets");
}

/** Import a gene set from the site's own seed controls, without a turn. */
async function importGeneSet(api: ApiClient, siteId: string, name: string) {
  const [set] = siteControlSets(siteId);
  if (set === undefined) throw new Error(`the ${siteId} seeds carry no control set`);
  const resp = await api.post("/api/v1/gene-sets/import", {
    data: { name, siteId, rawText: set.positive_ids.slice(0, 3).join("\n") },
  });
  expect(resp.status(), `import ${await resp.text()}`).toBe(201);
  return (await resp.json()) as GeneSet;
}

interface SeedFrame {
  type: string;
  message: string;
}

interface SeedCompleteFrame extends SeedFrame {
  type: "seed_complete";
  strategiesCreated: number;
  error: string | null;
}

/** The typed frames of one `/api/v1/seed` stream. */
function seedFrames(body: string): SeedFrame[] {
  return body
    .split("\n")
    .filter((line) => line.startsWith("data: ") && line.trim() !== "data: [DONE]")
    .map((line) => JSON.parse(line.slice("data: ".length)) as SeedFrame);
}

test.describe("Settings and account", () => {
  test("A1 - The model a turn runs on", async ({
    page,
    settingsPage,
    apiClient,
    siteId,
  }) => {
    const models = await readJson<ModelListResponse>(apiClient, "/api/v1/models");
    const tiers = await readJson<TierListResponse>(apiClient, "/api/v1/tiers");
    const provider = models.defaultProvider;
    const roles = rolesForAssistant(tiers.presets, DEFAULT_ASSISTANT_ID, provider);
    const tierNames = Object.keys(
      presetsForProvider(tiers.presets, DEFAULT_ASSISTANT_ID, provider),
    );
    const other = tierNames.find((tier) => tier !== models.defaultTier) ?? "";
    await openSite(page, siteId);

    await settingsPage.open();
    await expect(settingsDialog(page).getByRole("tab")).toHaveText(TAB_LABELS);
    await settingsPage.close();
    await page.getByRole("button", { name: "AI model settings" }).click();
    const dialog = settingsDialog(page);
    await expect(
      dialog.getByRole("tab", { name: "Model", exact: true }),
    ).toHaveAttribute("aria-selected", "true");

    await expect(dialog).toContainText(
      `${assistantLabel(DEFAULT_ASSISTANT_ID)} runs each stage below on its own model.`,
    );
    expect(roles.map(phaseLabel)).toEqual([
      "Assistant",
      "Planning",
      "Building",
      "Checking",
    ]);
    for (const role of roles) {
      const fallback = models.models.find((m) => m.id === models.phaseDefaults[role]);
      expect(fallback?.name, `the default model of ${role}`).not.toBe(undefined);
      const row = dialog.getByTestId(`phase-row-${role}`);
      await expect(row).toContainText(phaseLabel(role));
      await expect(row).toContainText(`Default: ${fallback?.name ?? ""}`);
    }
    const presets = dialog.getByRole("button", {
      name: /^(Quality|Balanced|Default|Fast)$/,
    });
    await expect(presets).toHaveText(["Quality", "Balanced", "Default", "Fast"]);
    const deployed = dialog.getByRole("button", {
      name: TIER_LABELS[models.defaultTier] ?? "",
      exact: true,
    });
    await expect(deployed).toHaveAttribute("aria-pressed", "true");

    const picked = dialog.getByRole("button", {
      name: TIER_LABELS[other] ?? "",
      exact: true,
    });
    await picked.click();
    await expect(picked).toHaveAttribute("aria-pressed", "true");
    await expect(deployed).toHaveAttribute("aria-pressed", "false");
    await expect(dialog.getByText(/^Default: /)).toHaveCount(0);

    await dialog
      .getByTestId(`phase-row-${roles[0] ?? ""}`)
      .getByRole("button", { name: /^Select model: / })
      .click();
    const catalog = page.getByRole("dialog", { name: "Model Catalog", exact: true });
    await expect(catalog.getByRole("columnheader")).toContainText([
      "Model",
      "Context",
      "Input $/MTok",
      "Output $/MTok",
      "Cached $/MTok",
      "Best For",
    ]);
    for (const model of models.models) {
      const row = catalog
        .getByRole("row")
        .filter({ has: page.getByText(model.name, { exact: true }) });
      await expect(row).toHaveCount(1);
      await expect(row).toContainText(formatCompactClean(model.contextSize ?? 0));
      await expect(row).toContainText(formatPrice(model.inputPrice ?? 0));
      await expect(row).toContainText(formatPrice(model.outputPrice ?? 0));
      await expect(row).toContainText(formatPrice(model.cachedInputPrice ?? 0));
      const reads = readsLabel(model);
      if (reads !== null) await expect(row).toContainText(reads);
    }
    await catalog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(catalog).toHaveCount(0);

    await dialog.getByRole("tab", { name: "Advanced", exact: true }).click();
    page.once("dialog", (confirm) => void confirm.accept());
    await dialog.getByRole("button", { name: "Reset all local settings" }).click();
    await expect(dialog).toHaveCount(0, { timeout: 30_000 });
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });
    await openSettingsTab(page, settingsPage, "Model");
    await expect(deployed).toHaveAttribute("aria-pressed", "true");
    await expect(picked).toHaveAttribute("aria-pressed", "false");
    await expect(dialog.getByText(/^Default: /)).toHaveCount(roles.length);
  });

  test("A2 - A researcher's own provider key", async ({
    page,
    settingsPage,
    siteId,
  }) => {
    await openSite(page, siteId);
    await openSettingsTab(page, settingsPage, "Provider keys");
    await expect(settingsDialog(page)).toContainText("Your own provider keys");
    await expect(
      settingsDialog(page).getByText("This deployment does not accept personal keys.", {
        exact: true,
      }),
    ).toBeVisible();
  });

  test(
    "A3 - The usage figures",
    { tag: "@turn" },
    async ({ chatPage, apiClient, page, siteId }) => {
      test.setTimeout(600_000);
      const quota = () => readJson<QuotaResponse>(apiClient, "/api/v1/me/quota");
      const before = await quota();

      const id = await buildOn(
        chatPage,
        siteId,
        prompt("single", S1_TEXT(siteOrganism(siteId))),
      );
      await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
      const turn = await fetchLastTurnUsage(apiClient, id);

      const chips = chatPage.assistantMessages.getByTestId("trace-usage");
      await expect(chips).toHaveCount(1, { timeout: 60_000 });
      await expect(chips).toHaveAttribute("title", "This turn");
      const chipText = normalize(await chips.textContent());
      expect(chipUsage(chipText)).toBe(formatUsage(turn.totalTokens, turn.costUsd));

      const footer = page.getByTestId("conversation-usage");
      const footerLine = `Conversation · ${formatTokens(turn.totalTokens)} tokens · ${formatCost(
        Number(turn.costUsd),
      )}`;
      await expect(footer).toHaveText(footerLine, { timeout: 30_000 });
      await footer.hover();
      const breakdown = tooltip(page, "This conversation's total across all turns.");
      await expect(breakdown).toBeVisible();
      await expect(breakdown).toContainText("Assistant");
      await expect(breakdown).toContainText("Sub-agents");
      await expect(breakdown).toContainText(
        `Total${formatUsage(turn.totalTokens, turn.costUsd)}`,
      );

      // The title call is charged beside the turn, so the quota grows by at least the turn.
      await expect
        .poll(async () => (await quota()).totalTokens - before.totalTokens, {
          timeout: 60_000,
        })
        .toBeGreaterThanOrEqual(turn.totalTokens);
      const after = await quota();
      expect(Number(after.usedUsd) - Number(before.usedUsd)).toBeGreaterThanOrEqual(
        Number(turn.costUsd) - 0.01,
      );
      await page.reload();
      const pill = page.getByLabel("Monthly quota");
      await expect(pill).toHaveText(
        `${formatCost(Number(after.usedUsd))} / ${limitFormat.format(Number(after.limitUsd))}`,
        { timeout: 30_000 },
      );
      await pill.hover();
      const account = tooltip(
        page,
        "Account total this month, across all conversations.",
      );
      await expect(account).toBeVisible();
      const resets = new Date(after.resetsAt).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
      await expect(account).toContainText(
        `${formatTokens(after.totalTokens)} tokens · resets ${resets}`,
      );

      await chatPage.sendAndSettle(prompt("recap", COUNT_QUESTION));
      await expect(chips).toHaveCount(2, { timeout: 60_000 });
      const second = await fetchLastTurnUsage(apiClient, id);
      const [first, next] = (await chips.allTextContents()).map(normalize);
      expect(first).toBe(chipText);
      expect(chipUsage(next ?? "")).toBe(
        formatUsage(second.totalTokens, second.costUsd),
      );
      await expect(footer).not.toHaveText(footerLine);
    },
  );

  test("A4 - The data tab", async ({
    chatPage,
    sidebarPage,
    settingsPage,
    apiClient,
    page,
    siteId,
  }) => {
    test.setTimeout(300_000);
    const otherSite = siteId === "toxodb" ? "plasmodb" : "toxodb";
    const siteName = siteShortName(siteId);
    await chatPage.startOn(siteId);
    await chatPage.sendTurn("A4 data tab", /\[mock\]/);
    const conversationId = chatPage.lastStrategyId ?? "";
    await importGeneSet(apiClient, siteId, "UAT A4 here");
    const kept = await importGeneSet(apiClient, otherSite, "UAT A4 elsewhere");

    await openSettingsTab(page, settingsPage, "Data");
    const dialog = settingsDialog(page);
    for (const action of [
      "Clear strategies",
      "Clear site data",
      "Clear ALL data",
      "Clear ALL + VEuPathDB",
    ]) {
      await expect(
        dialog.getByRole("button", { name: action, exact: true }),
      ).toBeVisible();
    }
    await expect(dialog).toContainText(
      `Remove every conversation for ${siteName} from PathFinder.`,
    );
    await expect(dialog).toContainText(
      `Delete the gene sets, runs and control sets for ${siteName}, and move every conversation on it to Recently deleted.`,
    );
    await expect(dialog).toContainText(
      "Delete the gene sets, runs and control sets on every site, and your memories with them.",
    );
    await expect(dialog.getByTestId("wdk-purge-description")).toContainText(
      "and the strategies PathFinder created in VEuPathDB",
    );

    await dialog.getByRole("button", { name: "Clear site data", exact: true }).click();
    const sitePurge = purgeResponse(page);
    await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
    // The page reloads on the answer, so its body is read as state afterwards.
    expect((await sitePurge).status()).toBe(200);
    await expect(dialog).toHaveCount(0, { timeout: 30_000 });

    expect(await geneSetsOn(apiClient, siteId)).toEqual([]);
    expect((await geneSetsOn(apiClient, otherSite)).map((set) => set.id)).toEqual([
      kept.id,
    ]);
    expect(await listConversations(apiClient, siteId)).toEqual([]);
    const dismissed = await listConversations(apiClient, siteId, "dismissed");
    expect(dismissed.map((row) => row.id)).toEqual([conversationId]);
    await openSite(page, siteId);
    await sidebarPage.expectDismissedCount(1);

    await openSettingsTab(page, settingsPage, "Data");
    await dialog
      .getByRole("button", { name: "Clear ALL + VEuPathDB", exact: true })
      .click();
    const confirm = dialog.getByRole("button", { name: "Confirm", exact: true });
    await expect(confirm).toBeDisabled();
    await dialog.getByPlaceholder("delete my data").fill("delete my data");
    await expect(confirm).toBeEnabled();
    const allPurge = purgeResponse(page);
    await confirm.click();
    const allResult = (await (await allPurge).json()) as PurgeUserDataResponse;
    expect(allResult.deleted.wdkStrategiesKept).toBe(0);
    await expect(page.getByText("Data cleared", { exact: true })).toBeVisible();
    await expect(
      page.getByText(
        `VEuPathDB strategies deleted: ${String(allResult.deleted.wdkStrategies)}. Memories deleted: ${String(allResult.deleted.memories)}.`,
        { exact: true },
      ),
    ).toBeVisible();
    await expect.poll(async () => (await geneSetsOn(apiClient)).length).toBe(0);
    const everywhere = await listBody<ConversationRow>(
      await apiClient.get("/api/v1/conversations/dismissed"),
      "dismissed conversations",
    );
    expect(everywhere).toEqual([]);
  });

  test("A5 - Privacy", async ({ page, settingsPage, siteId }) => {
    await openSite(page, siteId);
    await openSettingsTab(page, settingsPage, "Privacy");
    const dialog = settingsDialog(page);
    await expect(
      dialog.getByText("Improving PathFinder", { exact: true }),
    ).toBeVisible();
    await expect(dialog).toContainText(
      "PathFinder improves by learning from real strategies.",
    );
    const consent = dialog.getByRole("checkbox", {
      name: "Let PathFinder learn from my strategies",
    });
    await expect(consent).toBeVisible();
    const was = await consent.isChecked();

    const saved = page.waitForResponse(
      (r) => r.url().includes("/api/v1/me/privacy") && r.request().method() === "PATCH",
    );
    // The box follows the saved answer, so it changes after the PATCH returns.
    await consent.click();
    expect((await saved).ok()).toBe(true);
    await expect(consent).toBeChecked({ checked: !was });
    await page.reload();
    await expect(page.getByTestId("message-composer")).toBeVisible({ timeout: 60_000 });
    await openSettingsTab(page, settingsPage, "Privacy");
    if (was) await expect(consent).not.toBeChecked();
    else await expect(consent).toBeChecked();

    const restored = page.waitForResponse(
      (r) => r.url().includes("/api/v1/me/privacy") && r.request().method() === "PATCH",
    );
    await consent.click();
    expect((await restored).ok()).toBe(true);
    await expect(consent).toBeChecked({ checked: was });
  });

  test(
    "A6 - Advanced",
    { tag: "@turn" },
    async ({ chatPage, settingsPage, apiClient, page, siteId }) => {
      const id = await buildOn(
        chatPage,
        siteId,
        prompt("single", S1_TEXT(siteOrganism(siteId))),
      );
      const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
      const reply = chatPage.assistantReply(countPattern(counts.root));
      await expect(reply.getByTestId("trace-usage")).toHaveCount(1, {
        timeout: 60_000,
      });
      const footer = page.getByTestId("conversation-usage");
      await expect(footer).toBeVisible();

      await openSettingsTab(page, settingsPage, "Advanced");
      await settingsDialog(page)
        .getByRole("checkbox", { name: "Display token counts under each message" })
        .setChecked(false);
      await settingsPage.close();
      await expect(reply.getByTestId("trace-usage")).toHaveCount(0);
      await expect(footer).toBeVisible();

      await openSettingsTab(page, settingsPage, "Advanced");
      await settingsDialog(page)
        .getByRole("checkbox", {
          name: "Display raw JSON tool calls in the conversation",
        })
        .setChecked(true);
      await settingsPage.close();
      await openTrace(reply);
      const rows = reply.getByTestId("trace-row");
      await expect(rows).not.toHaveCount(0);
      const toggles = reply.getByRole("button", { name: "Raw", exact: true });
      await expect(toggles).toHaveCount(await rows.count());
      // A build turn reads the request once, so that row names one toggle.
      const buildCall = reply.getByTestId("tool-call-part").filter({
        has: page.getByTestId("trace-row").filter({ hasText: "Read the request" }),
      });
      await expect(buildCall).toHaveCount(1);
      const toggle = buildCall.getByRole("button", { name: "Raw", exact: true });
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      const raw = buildCall.getByTestId("trace-row-raw");
      await expect(raw.getByRole("heading", { name: "Parameters" })).toHaveCount(1);
      await expect(raw.getByRole("heading", { name: "Result" })).toHaveCount(1);
    },
  );

  test("A7 - Seeding", async ({
    sidebarPage,
    settingsPage,
    apiClient,
    page,
    siteId,
  }) => {
    test.setTimeout(600_000);
    await openSite(page, siteId);
    await openSettingsTab(page, settingsPage, "Seeding");
    const dialog = settingsDialog(page);
    const seedSite = dialog
      .getByRole("button")
      .filter({ hasText: siteShortName(siteId) });
    const seeded = page.waitForResponse(
      (r) =>
        r.url().includes(`/api/v1/seed?siteId=${siteId}`) &&
        r.request().method() === "POST",
      { timeout: 480_000 },
    );
    await seedSite.click();
    await expect(seedSite).toBeDisabled();
    const stream = await seeded;
    expect(stream.ok()).toBe(true);
    const frames = seedFrames(await stream.text());
    const complete = frames.find(
      (f): f is SeedCompleteFrame => f.type === "seed_complete",
    );
    if (complete === undefined)
      throw new Error("the seed stream carried no seed_complete");
    expect(complete.error).toBe(null);
    expect(complete.strategiesCreated).toBeGreaterThan(0);
    await expect(dialog.getByText(complete.message, { exact: true })).toBeVisible();
    await expect(seedSite).toBeEnabled();
    await settingsPage.close();

    const active = await listConversations(apiClient, siteId);
    const linked = active.filter((row) => row.wdkStrategyId != null);
    expect(linked.length).toBeGreaterThanOrEqual(complete.strategiesCreated);
    await sidebarPage.refresh();
    await expect(sidebarPage.items).toHaveCount(active.length, { timeout: 30_000 });

    await openSettingsTab(page, settingsPage, "Data");
    await dialog.getByRole("button", { name: "Clear site data", exact: true }).click();
    const purge = purgeResponse(page);
    await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
    expect((await purge).ok()).toBe(true);
    expect(await listConversations(apiClient, siteId)).toEqual([]);
    const dismissed = await listConversations(apiClient, siteId, "dismissed");
    expect(dismissed).toHaveLength(active.length);

    for (const row of dismissed) {
      const gone = await apiClient.delete(
        `/api/v1/conversations/${row.id}?deleteFromWdk=true`,
      );
      expect(gone.ok(), `delete ${row.id}: ${gone.status()}`).toBe(true);
    }
    expect(await listConversations(apiClient, siteId, "dismissed")).toEqual([]);
    for (const { wdkStrategyId } of linked) {
      const reopen = await apiClient.post("/api/v1/conversations/open", {
        data: { siteId, wdkStrategyId },
      });
      expect(reopen.ok(), `strategy ${String(wdkStrategyId)} survived on WDK`).toBe(
        false,
      );
    }
  });
});
