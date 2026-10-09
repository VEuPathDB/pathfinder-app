import { describe, expect, it, vi } from "vitest";

import { goToSiteSignIn, signInHref } from "./siteSignIn";

const LOGIN = "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login";
const ORIGIN = "https://muharram.veupathdb.org";

interface StubPage {
  win: Window;
  assign: ReturnType<typeof vi.fn>;
}

function page(href: string, parent?: Window): StubPage {
  const assign = vi.fn();
  const win = {
    location: { href, origin: new URL(href).origin, assign },
  } as unknown as Window & { parent: Window };
  win.parent = parent ?? win;
  return { win, assign };
}

function crossOriginParent(): Window {
  return {
    location: {
      get origin(): string {
        throw new DOMException("Blocked a frame", "SecurityError");
      },
    },
  } as unknown as Window;
}

describe("signInHref", () => {
  it("links to the website login and returns to this page", () => {
    expect(
      signInHref(
        "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login",
        "https://muharram.veupathdb.org/pathfinder/veupathdb/conversation",
      ),
    ).toBe(
      "https://muharram.veupathdb.org/eupathdb.amuharram/app/user/login?destination=" +
        encodeURIComponent(
          "https://muharram.veupathdb.org/pathfinder/veupathdb/conversation",
        ),
    );
  });

  it("adds the destination beside a query the sign-in address already has", () => {
    expect(
      signInHref(`${LOGIN}?lang=en`, "/pathfinder/plasmodb/conversation?a=1"),
    ).toBe(
      `${LOGIN}?lang=en&destination=%2Fpathfinder%2Fplasmodb%2Fconversation%3Fa%3D1`,
    );
  });

  it("keeps a sign-in address on this origin relative", () => {
    expect(
      signInHref(
        "/pathfinder/api/v1/dev/site-login",
        "/pathfinder/plasmodb/conversation",
      ),
    ).toBe(
      "/pathfinder/api/v1/dev/site-login?destination=%2Fpathfinder%2Fplasmodb%2Fconversation",
    );
  });
});

describe("goToSiteSignIn", () => {
  it("returns an unframed page to itself", () => {
    const here = page(`${ORIGIN}/pathfinder/plasmodb/conversation/abc?step=2`);

    goToSiteSignIn(here.win, LOGIN);

    expect(here.assign.mock.calls).toEqual([
      [signInHref(LOGIN, `${ORIGIN}/pathfinder/plasmodb/conversation/abc?step=2`)],
    ]);
  });

  it("sends the website page that frames PathFinder to the login, returning to that page", () => {
    const website = page(
      `${ORIGIN}/eupathdb.amuharram/app/pathfinder/plasmodb/conversation`,
    );
    const frame = page(`${ORIGIN}/pathfinder/plasmodb/conversation`, website.win);

    goToSiteSignIn(frame.win, LOGIN);

    expect(website.assign.mock.calls).toEqual([
      [
        signInHref(
          LOGIN,
          `${ORIGIN}/eupathdb.amuharram/app/pathfinder/plasmodb/conversation`,
        ),
      ],
    ]);
    expect(frame.assign).not.toHaveBeenCalled();
  });

  it("keeps a page framed by another origin to itself", () => {
    const frame = page(
      `${ORIGIN}/pathfinder/plasmodb/conversation`,
      crossOriginParent(),
    );

    goToSiteSignIn(frame.win, LOGIN);

    expect(frame.assign.mock.calls).toEqual([
      [signInHref(LOGIN, `${ORIGIN}/pathfinder/plasmodb/conversation`)],
    ]);
  });
});
