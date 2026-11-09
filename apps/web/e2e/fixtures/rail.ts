import type { Page } from "@playwright/test";

/** Open the rail's Review panel and unfold the assistant's notes. */
export async function openNotes(page: Page): Promise<void> {
  const review = page.getByRole("button", { name: "Open Review", exact: true });
  if ((await review.count()) > 0) await review.click();
  const fold = page
    .getByRole("region", { name: "Review detail", exact: true })
    .getByRole("button", { name: /^Assistant's notes/ });
  if ((await fold.getAttribute("aria-expanded")) !== "true") await fold.click();
}
