import { AxeBuilder } from "@axe-core/playwright";

import { test, expect } from "../fixtures/test";

/**
 * Feature: the active conversation row reads on the other site palettes, and a
 * viewer who asked for reduced motion sees it settled from its first paint.
 * The project's own site is audited by L4 in `uat/layout-access.spec.ts`.
 *
 * The row is tinted with the site's primary; its timestamp is a foreground
 * tone over that tint, and axe holds it to the 4.5:1 body-text ratio. An
 * entrance animation that ignores the preference paints the row at a fraction
 * of its opacity, which is where an audit reads the text below that ratio.
 */
for (const siteId of ["veupathdb", "fungidb", "toxodb"]) {
  test(
    `the active conversation row meets the contrast ratio on ${siteId}`,
    {
      tag: "@named-site",
    },
    async ({ page, chatPage, sidebarPage, sitePicker }) => {
      await chatPage.goto();
      await sitePicker.selectSite(siteId);
      await sitePicker.expectCurrentSite(siteId);
      await chatPage.send("first conversation");
      await chatPage.expectAssistantMessage(/\[mock\]/);
      await sidebarPage.expectAtLeastOneConversation();
      await page.mouse.move(0, 0);

      const result = await new AxeBuilder({ page })
        .include('[data-testid="conversation-item"]')
        .withRules(["color-contrast"])
        .analyze();

      const details = result.violations.flatMap((v) =>
        v.nodes.map((n) => `${n.html}: ${n.any.map((c) => c.message).join(" ")}`),
      );
      expect(details, details.join("\n")).toEqual([]);
    },
  );
}

test("a new conversation row is painted settled under reduced motion", async ({
  page,
  chatPage,
  sidebarPage,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await chatPage.goto();
  await page.evaluate(() => {
    const painted: string[] = [];
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof HTMLElement)) continue;
          const row = node.querySelector('[data-testid="conversation-item"]');
          if (row === null) continue;
          const wrapper = row.parentElement;
          painted.push(wrapper === null ? "" : getComputedStyle(wrapper).opacity);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    Object.assign(window, { __rowsPaintedAt: painted });
  });
  await chatPage.newChat();

  await chatPage.send("first conversation");
  await chatPage.expectAssistantMessage(/\[mock\]/);
  await sidebarPage.expectAtLeastOneConversation();

  const painted = await page.evaluate(
    () => (window as unknown as { __rowsPaintedAt: string[] }).__rowsPaintedAt,
  );
  expect(painted.length).toBeGreaterThan(0);
  expect(painted).toEqual(painted.map(() => "1"));
});
