/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

const offered = vi.hoisted(() => ({ value: true }));
vi.mock("@/app/hooks/useCurrentSite", () => ({
  useCurrentSite: () => ({
    siteId: "plasmodb",
    isPortal: false,
    conversationSite: null,
    offersAudits: offered.value,
  }),
}));

import AuditsLayout from "./layout";

describe("the audits section", () => {
  it("shows its pages on a site that offers audits", () => {
    offered.value = true;
    render(
      <AuditsLayout>
        <p>runs</p>
      </AuditsLayout>,
    );
    expect(screen.getByText("runs")).toBeVisible();
  });

  it("says audits are not offered on any other site, and shows no page", () => {
    offered.value = false;
    render(
      <AuditsLayout>
        <p>runs</p>
      </AuditsLayout>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "The gene model audit is not offered on this site.",
    );
    expect(screen.queryByText("runs")).toBeNull();
  });
});
