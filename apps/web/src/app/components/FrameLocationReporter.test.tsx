// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  Suspense,
  createContext,
  startTransition,
  use,
  useContext,
  useState,
} from "react";

const Address = createContext({ pathname: "/", query: "" });
vi.mock("next/navigation", () => ({
  usePathname: () => useContext(Address).pathname,
  useSearchParams: () => new URLSearchParams(useContext(Address).query),
}));

import { FrameLocationReporter } from "./FrameLocationReporter";

function at(pathname: string, query = "") {
  return (
    <Address value={{ pathname, query }}>
      <FrameLocationReporter />
    </Address>
  );
}

function frameUnderWebsitePage(): ReturnType<typeof vi.fn> {
  const postMessage = vi.fn();
  vi.stubGlobal("parent", {
    location: { origin: window.location.origin },
    postMessage,
  });
  return postMessage;
}

function postedMessages(postMessage: ReturnType<typeof vi.fn>): unknown[] {
  return postMessage.mock.calls.map(([message]) => message);
}

async function settle(): Promise<void> {
  await act(async () => {});
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("FrameLocationReporter", () => {
  it("posts each distinct path once to the website page that frames it", async () => {
    const postMessage = frameUnderWebsitePage();

    const { rerender } = render(at("/plasmodb/conversation"));
    await settle();
    rerender(at("/plasmodb/conversation"));
    await settle();
    rerender(at("/plasmodb/conversation/abc", "step=2"));
    await settle();

    expect(postMessage.mock.calls).toEqual([
      [
        { type: "pathfinder:location", path: "/plasmodb/conversation" },
        window.location.origin,
      ],
      [
        { type: "pathfinder:location", path: "/plasmodb/conversation/abc?step=2" },
        window.location.origin,
      ],
    ]);
  });

  it("posts nothing when the page is not framed", async () => {
    const postMessage = vi.spyOn(window, "postMessage");

    render(at("/giardiadb/conversation"));
    await settle();

    expect(window.parent).toBe(window);
    expect(postMessage).not.toHaveBeenCalled();
  });

  it("posts a path once under Strict Mode", async () => {
    const postMessage = frameUnderWebsitePage();

    render(at("/cryptodb/conversation"), { reactStrictMode: true });
    await settle();

    expect(postedMessages(postMessage)).toEqual([
      { type: "pathfinder:location", path: "/cryptodb/conversation" },
    ]);
  });

  it("posts only committed paths, never one whose navigation did not finish", async () => {
    const postMessage = frameUnderWebsitePage();
    const never = new Promise<never>(() => {});

    function Page({ pathname }: { pathname: string }) {
      if (pathname === "/b") use(never);
      return <p data-testid="shown">{pathname}</p>;
    }

    function Shell() {
      const [pathname, setPathname] = useState("/a");
      return (
        <Address value={{ pathname, query: "" }}>
          <FrameLocationReporter />
          <button onClick={() => startTransition(() => setPathname("/b"))}>to b</button>
          <button onClick={() => startTransition(() => setPathname("/a"))}>to a</button>
          <Suspense fallback={<p>loading</p>}>
            <Page pathname={pathname} />
          </Suspense>
        </Address>
      );
    }

    render(<Shell />);
    await settle();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "to b" })),
    );
    expect(screen.getByTestId("shown")).toHaveTextContent("/a");
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "to a" })),
    );
    await settle();

    expect(screen.getByTestId("shown")).toHaveTextContent("/a");
    expect(postedMessages(postMessage)).toEqual([
      { type: "pathfinder:location", path: "/a" },
    ]);
  });
});
