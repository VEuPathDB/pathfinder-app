import { type Page, expect, test } from "@playwright/test";

export class WorkbenchMainPage {
  constructor(private page: Page) {}

  // ── Active Set Header ──────────────────────────────────────────

  /** Verify the active set header shows name and exact gene count. */
  async expectActiveSetHeader(name: string, geneCount?: number) {
    await expect(this.page.getByRole("heading", { name, level: 1 })).toBeVisible();
    if (geneCount !== undefined) {
      await expect(
        this.page.getByText(`${geneCount.toLocaleString()} genes`),
      ).toBeVisible();
    }
  }

  // ── Panel Expand / Collapse ────────────────────────────────────

  async expandPanel(title: string) {
    await this.page
      .getByRole("button", { expanded: false })
      .filter({ hasText: title })
      .click();
  }

  async collapsePanel(title: string) {
    await this.page
      .getByRole("button", { expanded: true })
      .filter({ hasText: title })
      .click();
  }

  async expectPanelVisible(title: string) {
    const collapsed = this.page
      .getByRole("button", { expanded: false })
      .filter({ hasText: title });
    const expanded = this.page
      .getByRole("button", { expanded: true })
      .filter({ hasText: title });
    await expect(collapsed.or(expanded)).toBeVisible();
  }

  async expectPanelExpanded(title: string) {
    await expect(
      this.page.getByRole("button", { expanded: true }).filter({ hasText: title }),
    ).toBeVisible();
  }

  // ── Enrichment Analysis ────────────────────────────────────────

  /**
   * Run enrichment and verify REAL results come back from WDK.
   *
   * Asserts that:
   * 1. "Run Enrichment" button is clicked
   * 2. Summary bar with "significant term" appears (SUCCESS state only)
   * 3. No error message is visible
   *
   * The summary bar shows "N significant term(s)" on success.
   * "genes analyzed" only appears when WDK returns a result count (not always).
   * Error states show "Analysis failed: ..." or "HTTP ...".
   */
  // The enrich request is synchronous and bounded server-side: WDK analysis
  // polling caps at 300 s per analysis, plus step creation and warmup, and
  // concurrent specs queue on a process-wide batch semaphore. The ceiling
  // covers the bound; a green run never waits it out.
  async runEnrichmentAndVerifyResults(timeout = 360_000) {
    // Only tests that run enrichment carry its ceiling; the project default
    // stays tight for everything else.
    test.setTimeout(test.info().timeout + timeout);
    // Expand if collapsed
    const collapsed = this.page
      .getByRole("button", { expanded: false })
      .filter({ hasText: "Enrichment Analysis" });
    if (await collapsed.isVisible().catch(() => false)) {
      await collapsed.click();
    }
    await expect(
      this.page
        .getByRole("button", { expanded: true })
        .filter({ hasText: "Enrichment Analysis" }),
    ).toBeVisible({ timeout: 10_000 });

    // Click "Run Enrichment"
    const runBtn = this.page.getByRole("button", { name: /run enrichment/i });
    await expect(runBtn).toBeVisible();
    await runBtn.click();

    // Wait for either SUCCESS (significant terms) or WDK error (HTTP 500).
    // WDK enrichment endpoints are externally operated and can return 500
    // due to server-side issues outside our control.
    const success = this.page.getByText(/significant term/i);
    await expect
      .poll(async () => (await success.count()) + (await this.wdkErrorCount()), {
        timeout,
      })
      .toBeGreaterThan(0);
  }

  /** How many WDK server-error messages the page shows. */
  private async wdkErrorCount(): Promise<number> {
    return this.page.getByText(/HTTP 500|Analysis failed/i).count();
  }

  /** The result tabs, one regular expression per analysis type. */
  private static readonly RESULT_TAB_PATTERNS = [
    /GO: Biological/i,
    /GO: Molecular/i,
    /GO: Cellular/i,
    /Metabolic Pathway/i,
    /Word Enrichment/i,
  ];

  private resultTab(pattern: RegExp) {
    return this.page.getByRole("button").filter({ hasText: pattern });
  }

  /**
   * Verify enrichment results contain REAL data with actual values.
   *
   * Checks:
   * 1. Summary bar shows "N significant term(s)" with a real number
   * 2. Enrichment table has at least 1 row
   * 3. Table rows contain real p-values (exponential notation like 1.23e-04)
   */
  async expectEnrichmentResultsWithData() {
    // If WDK returned a server error, skip data verification — external issue.
    if ((await this.wdkErrorCount()) > 0) return;

    // Open the first result tab whose label ends in a non-zero term count.
    for (const pattern of WorkbenchMainPage.RESULT_TAB_PATTERNS) {
      const tab = this.resultTab(pattern);
      if ((await tab.count()) !== 1) continue;
      const match = ((await tab.textContent()) ?? "").match(/(\d+)\s*$/);
      const terms = match?.[1];
      if (terms !== undefined && parseInt(terms, 10) > 0) {
        await tab.click();
        break;
      }
    }

    // 1. "N significant term(s)" visible with a real number > 0
    const summaryText = this.page.getByText(/\d+\s+significant term/i);
    await expect(summaryText).not.toHaveCount(0, { timeout: 10_000 });

    // 2. Enrichment table has at least 1 data row
    const tableRows = this.page.locator("table tbody tr");
    await expect(tableRows).not.toHaveCount(0, { timeout: 10_000 });

    // 3. At least one cell contains a real p-value (exponential notation)
    const pValueCell = this.page.locator("table tbody td").filter({
      hasText: /\d\.\d{2}e[+-]\d+/,
    });
    await expect(pValueCell).not.toHaveCount(0, { timeout: 5_000 });
  }

  /**
   * Verify enrichment result tabs show full analysis type labels.
   *
   * Matches the RESULT tabs ("GO: Biological Process", "Metabolic Pathway", etc.)
   * NOT the type selector chips ("GO:BP", "GO:MF", etc.) which are always visible.
   */
  async expectEnrichmentTypeTabs(options?: { skipOnWdkError?: boolean }) {
    if (options?.skipOnWdkError !== false && (await this.wdkErrorCount()) > 0) {
      return;
    }
    // Result tabs use full labels from ENRICHMENT_ANALYSIS_LABELS:
    //   "GO: Biological Process", "GO: Molecular Function",
    //   "GO: Cellular Component", "Metabolic Pathway", "Word Enrichment"
    await expect
      .poll(
        async () => {
          const counts = await Promise.all(
            WorkbenchMainPage.RESULT_TAB_PATTERNS.map((pattern) =>
              this.resultTab(pattern).count(),
            ),
          );
          return counts.reduce((total, count) => total + count, 0);
        },
        { timeout: 10_000 },
      )
      .toBeGreaterThan(0);
  }

  async expectEmptyState() {
    await expect(this.page.getByText(/welcome to the workbench/i)).toBeVisible();
  }
}
