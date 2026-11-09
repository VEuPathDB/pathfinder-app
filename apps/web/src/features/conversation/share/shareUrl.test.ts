import { describe, expect, it } from "vitest";

import { shareUrl } from "./shareUrl";

describe("shareUrl", () => {
  it("opens the link inside the website page that hosts PathFinder", () => {
    expect(
      shareUrl(
        "tok-1",
        "https://qa.plasmodb.org/plasmo.qa/app/pathfinder",
        "https://qa.plasmodb.org",
      ),
    ).toBe("https://qa.plasmodb.org/plasmo.qa/app/pathfinder/shared/tok-1");
  });

  it("falls back to PathFinder's own address when no site hosts it", () => {
    expect(shareUrl("tok-1", null, "http://localhost:3000")).toBe(
      "http://localhost:3000/pathfinder/shared/tok-1",
    );
  });
});
