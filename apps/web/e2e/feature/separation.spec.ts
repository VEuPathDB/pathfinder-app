import { test, expect } from "../fixtures/a11y";

/** The mock Lead's separation arc: the controls of the seed "PF3D7 Signal
 * Peptide Genes", run in exact mode. */
const SEPARATION_PROMPT = "Separate my controls: the signal peptide seed, exact";

/**
 * Feature: a strategy from positive and negative controls.
 *
 * Real WDK API, real DB, real worker. Only the LLM is mocked.
 *
 * Flow: the run's approval, the worker's measurements, the result and its
 * adoption card, a yes that builds the measured strategy, and the check that
 * tests it with the controls it was measured on, which leaves an evidence card.
 */
test.describe("A strategy from controls", () => {
  test("the run offers a measured strategy and a yes builds and checks it", async ({
    chatPage,
    page,
    sitePicker,
  }) => {
    test.setTimeout(900_000);
    await chatPage.goto();
    await sitePicker.selectSite("plasmodb");

    await chatPage.send(SEPARATION_PROMPT);
    const runApproval = page.getByTestId("approval-card");
    await expect(runApproval.getByTestId("approval-card-title")).toContainText(
      "Run the separation?",
      { timeout: 90_000 },
    );
    await runApproval.getByTestId("tool-approval-approve").click();

    const result = page.getByTestId("data-separation-result");
    await expect(result).toBeVisible({ timeout: 600_000 });
    await expect(result.getByTestId("separation-cell-recovered")).toBeVisible();
    await expect(result.getByTestId("separation-requests")).toContainText(
      / of 200 requests/,
    );

    const card = page.getByTestId("separation-card");
    await expect(card.getByTestId("separation-question")).toContainText(
      /^Build the (separating strategy|closest strategy found): /,
      { timeout: 90_000 },
    );
    await card.getByRole("button", { name: "Yes" }).click();

    await expect(card.getByTestId("separation-decision")).toHaveText("You said yes.", {
      timeout: 90_000,
    });
    await expect(page.getByTestId("data-graph-snapshot")).toBeVisible({
      timeout: 180_000,
    });
    await expect(page.getByTestId("data-evidence-card")).toBeVisible({
      timeout: 600_000,
    });
    await chatPage.expectAssistantMessage(
      /I built the strategy the separation run measured/,
      {
        timeout: 600_000,
      },
    );
  });
});
