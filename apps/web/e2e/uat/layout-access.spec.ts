/**
 * UAT flows L1 to L5: the app at 1024 px and at a phone width, keyboard-only
 * use of the composer and the cards, the dark colours a host page turns on,
 * and the accessible names of the controls the flows use.
 */

import type { Locator, Page } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import type { ModelListResponse } from "@pathfinder/shared/generated/types/ModelListResponse";

import { DEFAULT_ASSISTANT_ID } from "@/lib/assistants";
import { attachLabel, readerModel } from "@/lib/models/attachments";

import { test, expect } from "../fixtures/test";
import { prompt } from "../fixtures/arcs";
import type { ApiClient } from "../fixtures/api-client";
import { LAYOUTS } from "../fixtures/arc-layouts";
import { expectBuild, expectEvidence } from "../fixtures/build-checks";
import { siteControlSets, siteOrganism } from "../fixtures/site-reads";
import type { ChatPage } from "../pages/chat.page";
import type { GraphPage } from "../pages/graph.page";
import { openConversationId } from "../pages/navigation";

const S1_TEXT = (organism: string) =>
  `Find ${organism} genes whose proteins have a predicted signal peptide.`;
const S2_TEXT = (organism: string) =>
  `Find ${organism} genes with a predicted signal peptide and 2 to 99 transmembrane domains.`;
const PROPOSAL_TEXT =
  "Offer me one change that would make this strategy more specific, as a proposal I can accept or decline. Do not change anything yet.";

/** How many key presses a keyboard walk may take before it gives up. */
const KEY_WALK_LIMIT = 400;

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

/** The page scrolls only vertically. */
async function noHorizontalScroll(page: Page): Promise<boolean> {
  return page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  );
}

/** The element shows all of its content across its width. */
async function unclipped(locator: Locator): Promise<boolean> {
  return locator.evaluate((el) => el.scrollWidth <= el.clientWidth);
}

/** Every canvas node lies inside the canvas pane. */
async function nodesInsidePane(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const pane = document.querySelector(".react-flow");
    if (pane === null) return false;
    const box = pane.getBoundingClientRect();
    const nodes = [...document.querySelectorAll("[data-testid^='rf-node-']")];
    return (
      nodes.length > 0 &&
      nodes.every((node) => {
        const r = node.getBoundingClientRect();
        return (
          r.left >= box.left - 1 &&
          r.right <= box.right + 1 &&
          r.top >= box.top - 1 &&
          r.bottom <= box.bottom + 1
        );
      })
    );
  });
}

/** The canvas zoom factor, read from the viewport transform. */
async function canvasScale(page: Page): Promise<number> {
  return page.evaluate(() => {
    const viewport = document.querySelector<HTMLElement>(".react-flow__viewport");
    const match = /scale\(([\d.]+)\)/.exec(viewport?.style.transform ?? "");
    return Number(match?.[1] ?? "0");
  });
}

/** Press `key` until `target` holds the focus. */
async function keyTo(page: Page, target: Locator, key: "Tab" | "Shift+Tab") {
  for (let presses = 0; presses < KEY_WALK_LIMIT; presses += 1) {
    if (await target.evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press(key);
  }
  await expect(target).toBeFocused();
}

/** The model that reads the user's message on this deployment's defaults. */
async function attachName(api: ApiClient): Promise<string> {
  const resp = await api.get("/api/v1/models");
  expect(resp.status()).toBe(200);
  const models = (await resp.json()) as ModelListResponse;
  return attachLabel(
    readerModel(DEFAULT_ASSISTANT_ID, {}, models.phaseDefaults, models.models),
  );
}

/** Open the canvas and wait for its topbar to settle. */
async function openCanvas(graphPage: GraphPage, siteId: string, id: string) {
  await graphPage.goToStrategy(siteId, id);
  await graphPage.expectStrategyTopbar();
  await expect(graphPage.strategyPageSyncState).toHaveAttribute(
    "data-sync-state",
    "idle",
    { timeout: 30_000 },
  );
  await expect(graphPage.nodes).not.toHaveCount(0);
}

function bodyBackground(page: Page): Promise<string> {
  return page.evaluate(() => getComputedStyle(document.body).backgroundColor);
}

test.describe("Layout and access", () => {
  test(
    "L1 - 1024 px wide",
    { tag: "@turn" },
    async ({ chatPage, graphPage, apiClient, page, siteId }) => {
      await page.setViewportSize({ width: 1024, height: 768 });
      const id = await buildOn(
        chatPage,
        siteId,
        prompt("intersect", S2_TEXT(siteOrganism(siteId))),
      );
      const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

      expect(await noHorizontalScroll(page)).toBe(true);
      await expect(chatPage.composer).toBeVisible();
      await expect(chatPage.sendButton).toBeVisible();
      await expect(page.getByTestId("conversation-usage")).toBeVisible();
      await expect(graphPage.railFooter).toHaveText("3 steps");
      expect(await unclipped(graphPage.railFooter)).toBe(true);

      const card = await expectEvidence(page, "Supported", counts.root);
      const clipped = await card
        .locator("td, th")
        .evaluateAll((cells) =>
          cells
            .filter((cell) => cell.scrollWidth > cell.clientWidth)
            .map((cell) => cell.textContent),
        );
      expect(clipped).toEqual([]);

      await openCanvas(graphPage, siteId, id);
      expect(await unclipped(graphPage.strategyPageTopbar)).toBe(true);
      const zoomIn = graphPage.canvasControls.getByRole("button", { name: "Zoom in" });
      const fitted = await canvasScale(page);
      for (let presses = 0; presses < 4; presses += 1) await zoomIn.click();
      await expect.poll(() => canvasScale(page)).toBeGreaterThan(fitted);
      await graphPage.canvasControls
        .getByRole("button", { name: "Fit to view" })
        .click();
      await expect.poll(() => nodesInsidePane(page)).toBe(true);
      expect(await noHorizontalScroll(page)).toBe(true);
    },
  );

  test("L2 - Phone width", async ({ chatPage, page, siteId }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/${siteId}/conversation`);
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });

    const openSidebar = page.getByRole("button", { name: "Open conversation sidebar" });
    await expect(openSidebar).toHaveAttribute("aria-pressed", "false");
    await expect(
      page.getByRole("button", {
        name: /^Close (Strategy|Tasks|Memories|Notes|Progress|Studies)$/,
      }),
    ).toHaveCount(0);
    expect(await noHorizontalScroll(page)).toBe(true);

    await openSidebar.click();
    await expect(page.getByTestId("conversations-search-input")).toBeVisible();
    await page.getByRole("button", { name: "Collapse conversation sidebar" }).click();
    await expect(openSidebar).toHaveAttribute("aria-pressed", "false");

    await chatPage.messageInput.fill("/");
    const menu = page.getByTestId("slash-popover");
    await expect(menu).toBeVisible();
    const box = await menu.boundingBox();
    expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect(
      (box?.x ?? 0) + (box?.width ?? Number.POSITIVE_INFINITY),
    ).toBeLessThanOrEqual(390);
    expect(await noHorizontalScroll(page)).toBe(true);
  });

  test(
    "L3 - Keyboard only",
    { tag: "@turn" },
    async ({ chatPage, graphPage, apiClient, page, siteId }) => {
      test.setTimeout(900_000);
      const keyboard = page.keyboard;
      await page.goto(`/${siteId}/conversation`);
      await expect(chatPage.messageInput).toBeFocused({ timeout: 60_000 });

      await keyboard.type("first line");
      await keyboard.press("Shift+Enter");
      await keyboard.type("second line");
      await expect(chatPage.messageInput).toHaveValue("first line\nsecond line");
      await keyboard.press("Enter");
      await chatPage.expectAssistantMessage(/\[mock\]/, { timeout: 240_000 });
      await expect(chatPage.userMessage("second line")).toContainText("first line");
      const id = await openConversationId(page);

      await chatPage.messageInput.focus();
      await keyboard.type("/");
      const options = page.getByTestId("slash-popover").getByRole("option");
      await expect(options).not.toHaveCount(0);
      const names = await options.evaluateAll((els) =>
        els.map((el) =>
          (el.getAttribute("data-testid") ?? "").replace(/^slash-item-/, ""),
        ),
      );
      await keyboard.press("ArrowDown");
      await keyboard.press("ArrowDown");
      await expect(page.getByTestId(`slash-item-${names[2] ?? ""}`)).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await keyboard.press("Enter");
      const stepper = page.getByTestId("slash-param-stepper");
      await expect(stepper).toContainText(`/${names[2] ?? ""}`);
      await keyTo(page, stepper.getByRole("button", { name: "Cancel" }), "Shift+Tab");
      await keyboard.press("Enter");
      await expect(stepper).toHaveCount(0);
      await chatPage.messageInput.focus();
      await keyboard.type("/he");
      await expect(page.getByTestId("slash-popover")).toBeVisible();
      await keyboard.press("Escape");
      await expect(chatPage.messageInput).toHaveValue("");

      await chatPage.sendAndSettle(prompt("intersect", S2_TEXT(siteOrganism(siteId))));
      await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

      await chatPage.sendAndSettle(prompt("proposal", PROPOSAL_TEXT));
      const proposal = page.getByTestId("proposal-card");
      await expect(proposal).toBeVisible({ timeout: 60_000 });
      await chatPage.messageInput.focus();
      await keyTo(page, proposal.getByTestId("proposal-note"), "Shift+Tab");
      await keyboard.type("Not now: too narrow for what I need.");
      await keyTo(page, proposal.getByTestId("proposal-no"), "Tab");
      await keyboard.press("Enter");
      await expect(proposal.getByTestId("proposal-decision")).toHaveText(
        "You said no.",
      );
      await expectBuild(page, apiClient, id, siteId, LAYOUTS.intersect);

      await openCanvas(graphPage, siteId, id);
      const nodeCount = await graphPage.nodes.count();
      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement)
          document.activeElement.blur();
      });
      await keyboard.press("r");
      await expect(graphPage.nodes).toHaveCount(nodeCount);
      const tidy = await canvasScale(page);
      for (let presses = 0; presses < 3; presses += 1) await keyboard.press("=");
      await expect.poll(() => canvasScale(page)).toBeGreaterThan(tidy);
      await keyboard.press("f");
      await expect.poll(() => nodesInsidePane(page)).toBe(true);

      await page.goto(`/${siteId}/conversation/${id}`);
      await expect(chatPage.messageInput).toBeFocused({ timeout: 60_000 });
      await keyboard.type("/clear");
      await keyboard.press("Enter");
      const approval = page.getByTestId("approval-card");
      const approve = approval.getByTestId("tool-approval-approve");
      await expect(approve).toBeVisible({ timeout: 240_000 });
      await chatPage.messageInput.focus();
      await keyTo(page, approve, "Shift+Tab");
      await keyboard.press("Enter");
      await expect(page.getByTestId("tool-approval-decision")).toHaveText("Approved");
      await expect(chatPage.sendButton).toBeVisible({ timeout: 240_000 });

      await chatPage.messageInput.focus();
      const settingsButton = page.getByTestId("nav-rail-settings-button");
      await keyTo(page, settingsButton, "Shift+Tab");
      await keyboard.press("Enter");
      const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
      await expect(dialog).toBeVisible();
      const tabs = dialog.getByRole("tab");
      const labels = await tabs.allTextContents();
      await keyTo(
        page,
        dialog.getByRole("tab", { name: labels[0] ?? "", exact: true }),
        "Tab",
      );
      for (const [index, label] of labels.entries()) {
        if (index > 0) await keyboard.press("ArrowRight");
        const tab = dialog.getByRole("tab", { name: label, exact: true });
        await expect(tab).toBeFocused();
        expect(await tab.evaluate((el) => el.matches(":focus-visible"))).toBe(true);
      }
      await keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
    },
  );

  test("L4 - Dark mode", async ({ chatPage, sidebarPage, page, siteId }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await chatPage.startOn(siteId);
    await chatPage.sendTurn("first conversation", /\[mock\]/);
    await sidebarPage.expectAtLeastOneConversation();
    await page.mouse.move(0, 0);
    const audit = await new AxeBuilder({ page })
      .include('[data-testid="conversation-item"]')
      .withRules(["color-contrast"])
      .analyze();
    const details = audit.violations.flatMap((v) =>
      v.nodes.map((n) => `${n.html}: ${n.any.map((c) => c.message).join(" ")}`),
    );
    expect(details, details.join("\n")).toEqual([]);

    const light = await bodyBackground(page);
    await page.emulateMedia({ colorScheme: "dark" });
    await page.reload();
    await expect(chatPage.composer).toBeVisible({ timeout: 60_000 });
    expect(await bodyBackground(page)).toBe(light);

    await page.evaluate(() => {
      document.documentElement.dataset["theme"] = "dark";
    });
    await expect.poll(() => bodyBackground(page)).not.toBe(light);
  });

  test(
    "L5 - Screen-reader names",
    { tag: "@turn" },
    async ({ chatPage, apiClient, page, siteId }) => {
      test.setTimeout(900_000);
      await chatPage.startOn(siteId);
      await expect(page.getByRole("log")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Send", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: await attachName(apiClient), exact: true }),
      ).toBeVisible();

      await chatPage.send(prompt("single", S1_TEXT(siteOrganism(siteId))));
      await expect(
        page.getByRole("button", { name: "Stop", exact: true }),
      ).toBeVisible();
      await chatPage.expectIdle(240_000);
      // A build opens the Strategy panel, so its toggle names the close.
      await expect(
        page
          .getByLabel("Right rail")
          .getByRole("button", { name: "Close Strategy", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Open Notes", exact: true }),
      ).toBeVisible();

      const id = chatPage.lastStrategyId ?? "";
      const counts = await expectBuild(page, apiClient, id, siteId, LAYOUTS.single);
      const reply = chatPage.assistantMessages.filter({
        has: page.getByTestId("data-evidence-card"),
      });
      await expect(reply).toHaveCount(1, { timeout: 60_000 });
      await reply.hover();
      for (const name of [
        "Good response",
        "Bad response",
        "Branch to a new conversation from here",
      ]) {
        await expect(reply.getByRole("button", { name, exact: true })).toBeVisible();
      }
      await expectEvidence(page, "Supported", counts.root);

      const sets = siteControlSets(siteId);
      const controls =
        sets.find((set) => /signal peptide/i.test(set.name)) ??
        sets.find((set) => /secret/i.test(set.name));
      if (controls === undefined)
        throw new Error(`no secreted control set on ${siteId}`);
      await chatPage.sendAndSettle(
        prompt(
          "controls-test",
          [
            "Test this strategy against my controls.",
            `Positive controls: ${controls.positive_ids.join(" ")}`,
            `Negative controls: ${controls.negative_ids.join(" ")}`,
          ].join("\n"),
        ),
      );
      const recovered = page.getByTestId("data-evidence-card").getByRole("button", {
        name: /^[\d,]+ positive controls recovered, click to copy the ids$/,
      });
      await expect(recovered).not.toHaveCount(0, { timeout: 480_000 });
    },
  );
});
