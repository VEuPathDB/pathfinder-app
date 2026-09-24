import { expect } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { test as baseTest } from "./test";
import { clearAllGeneSets } from "./api-client";

const BASE_URL = process.env["PLAYWRIGHT_BASE_URL"] ?? "http://localhost:3000";

interface SeriousViolation {
  id: string;
  nodes: number;
  impact: string;
  help: string;
  targets: string[];
  details: string[];
}

/**
 * Extends the project test fixture with an automatic accessibility audit
 * that runs after every test. Fails the test if any axe-core violation
 * with impact "serious" or "critical" is reported.
 *
 * Use this fixture instead of the base `test` for every journey spec: the
 * journeys exercise the breadth of the UI, so an a11y audit at end-of-test
 * catches real regressions.
 */
export const test = baseTest.extend({
  page: async ({ page }, use, testInfo) => {
    // Run with reduced motion so entrance animations don't leave text at
    // transient sub-contrast opacity when the post-test audit fires.
    await page.emulateMedia({ reducedMotion: "reduce" });
    // Journey specs are serial and read gene-set lists; start each from a
    // clean slate so set assertions are not polluted by leftovers.
    await clearAllGeneSets(page.context(), BASE_URL);
    await use(page);
    if (testInfo.status === "skipped") return;
    if (page.isClosed()) return;
    const result = await new AxeBuilder({ page }).analyze();
    const seriousAndCritical: SeriousViolation[] = result.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({
        id: v.id,
        nodes: v.nodes.length,
        impact: v.impact ?? "",
        help: v.help,
        targets: v.nodes.flatMap((n) => n.target.map((t) => String(t))),
        details: v.nodes.map(
          (n) =>
            `${n.html}\n        ${n.any
              .map((c) => `${c.message} ${JSON.stringify(c.data)}`)
              .join("\n        ")}`,
        ),
      }));
    expect(
      seriousAndCritical,
      `Accessibility violations (serious/critical) found:\n${seriousAndCritical
        .map(
          (v) =>
            `  - [${v.impact}] ${v.id} (${v.nodes} nodes): ${v.help}\n      ${v.details.join("\n      ")}`,
        )
        .join("\n")}`,
    ).toEqual([]);
  },
});

export { expect } from "@playwright/test";
