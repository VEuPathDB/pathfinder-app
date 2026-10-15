import { describe, expect, it, vi } from "vitest";

import { goToWebsitePage, reportLocation, sameOriginFramer } from "./frameBridge";

const ORIGIN = "https://muharram.veupathdb.org";

interface StubPage {
  win: Window;
  postMessage: ReturnType<typeof vi.fn>;
}

function page(origin: string, parent?: Window): StubPage {
  const postMessage = vi.fn();
  const win = {
    location: { origin },
    postMessage,
  } as unknown as Window & { parent: Window };
  win.parent = parent ?? win;
  return { win, postMessage };
}

function crossOriginPage(): StubPage {
  const postMessage = vi.fn();
  const win = {
    location: {
      get origin(): string {
        throw new DOMException("Blocked a frame", "SecurityError");
      },
    },
    postMessage,
  } as unknown as Window;
  return { win, postMessage };
}

describe("sameOriginFramer", () => {
  it("names no framer for a page that is not framed", () => {
    expect(sameOriginFramer(page(ORIGIN).win)).toBe(null);
  });

  it("names the parent of the same origin", () => {
    const website = page(ORIGIN);
    expect(sameOriginFramer(page(ORIGIN, website.win).win)).toBe(website.win);
  });

  it("names no framer for a parent that refuses to show its origin", () => {
    expect(sameOriginFramer(page(ORIGIN, crossOriginPage().win).win)).toBe(null);
  });

  it("names no framer for a parent of another origin", () => {
    const other = page("https://qa.plasmodb.org");
    expect(sameOriginFramer(page(ORIGIN, other.win).win)).toBe(null);
  });
});

describe("reportLocation", () => {
  it("posts the path to a same-origin parent, addressed to this origin", () => {
    const website = page(ORIGIN);
    const frame = page(ORIGIN, website.win);

    reportLocation(frame.win, "/plasmodb/conversation/1?step=2");

    expect(website.postMessage.mock.calls).toEqual([
      [
        { type: "pathfinder:location", path: "/plasmodb/conversation/1?step=2" },
        ORIGIN,
      ],
    ]);
    expect(frame.postMessage).not.toHaveBeenCalled();
  });

  it("posts nothing when the page is not framed", () => {
    const here = page(ORIGIN);

    reportLocation(here.win, "/plasmodb/conversation");

    expect(here.postMessage).not.toHaveBeenCalled();
  });

  it("posts nothing to a cross-origin parent and does not throw", () => {
    const other = crossOriginPage();
    const frame = page(ORIGIN, other.win);

    expect(() => reportLocation(frame.win, "/plasmodb/conversation")).not.toThrow();
    expect(other.postMessage).not.toHaveBeenCalled();
  });

  it("posts a path again only after another path was posted", () => {
    const website = page(ORIGIN);
    const frame = page(ORIGIN, website.win);

    for (const path of [
      "/toxodb/saved",
      "/toxodb/saved",
      "/toxodb/conversation",
      "/toxodb/saved",
    ]) {
      reportLocation(frame.win, path);
    }

    expect(website.postMessage.mock.calls.map(([message]) => message)).toEqual([
      { type: "pathfinder:location", path: "/toxodb/saved" },
      { type: "pathfinder:location", path: "/toxodb/conversation" },
      { type: "pathfinder:location", path: "/toxodb/saved" },
    ]);
  });
});

describe("goToWebsitePage", () => {
  const SITE_PAGE = `${ORIGIN}/eupathdb.amuharram/app/pathfinder`;

  function tab(origin: string, parent?: Window) {
    const replace = vi.fn();
    const win = { location: { origin, replace } } as unknown as Window & {
      parent: Window;
    };
    win.parent = parent ?? win;
    return { win, replace };
  }

  it("sends a page opened on its own to the website page for the same path", () => {
    const { win, replace } = tab(ORIGIN);

    goToWebsitePage(win, SITE_PAGE, "/veupathdb/conversation/c1?step=2");

    expect(replace.mock.calls).toEqual([
      [`${SITE_PAGE}/veupathdb/conversation/c1?step=2`],
    ]);
  });

  it("keeps a page the website page frames", () => {
    const { win: website } = tab(ORIGIN);
    const { win, replace } = tab(ORIGIN, website);

    goToWebsitePage(win, SITE_PAGE, "/veupathdb/conversation");

    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps a page on a host the website page is not on", () => {
    const { win, replace } = tab("http://localhost:3010");

    goToWebsitePage(win, SITE_PAGE, "/veupathdb/conversation");

    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps a page when the website address is not a URL", () => {
    const { win, replace } = tab(ORIGIN);

    goToWebsitePage(win, "not a url", "/veupathdb/conversation");

    expect(replace).not.toHaveBeenCalled();
  });
});
