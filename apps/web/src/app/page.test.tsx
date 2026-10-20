import { describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (url: string) => redirectMock(url),
}));

import RootPage from "./page";

describe("RootPage", () => {
  it("sends the bare root to the conversation of the site the website frames", () => {
    RootPage();

    expect(redirectMock.mock.calls).toEqual([["/conversation"]]);
  });
});
