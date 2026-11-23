import type * as TestingLibraryReact from "@testing-library/react";
import { createElement, type ComponentType, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { createTestQueryClient } from "./src/lib/query/testing";

// Polyfills for libraries (cmdk, radix) that assume browser globals jsdom
// doesn't ship by default.
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverPolyfill;
}
if (
  typeof Element !== "undefined" &&
  typeof (Element.prototype as Partial<Element>).scrollIntoView !== "function"
) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}
if (
  typeof Element !== "undefined" &&
  typeof (Element.prototype as Partial<Element>).scrollTo !== "function"
) {
  Element.prototype.scrollTo = function scrollTo() {};
}
if (
  typeof Element !== "undefined" &&
  typeof (Element.prototype as Partial<Element>).hasPointerCapture !== "function"
) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => {};
  Element.prototype.setPointerCapture = () => {};
}
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => true,
  });
}

type WrapperComponent = ComponentType<{ children: ReactNode }>;

function withQueryClient(Wrapper?: WrapperComponent): WrapperComponent {
  const queryClient = createTestQueryClient();

  function QueryClientWrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      Wrapper ? createElement(Wrapper, null, children) : children,
    );
  }

  return QueryClientWrapper;
}

vi.mock("@testing-library/react", async () => {
  const actual = await vi.importActual<typeof TestingLibraryReact>(
    "@testing-library/react",
  );

  return {
    ...actual,
    render: (
      ui: Parameters<typeof actual.render>[0],
      options?: Parameters<typeof actual.render>[1],
    ) =>
      actual.render(ui, {
        ...(options ?? {}),
        wrapper: withQueryClient(options?.wrapper as WrapperComponent | undefined),
      }),
    renderHook: <Result, Props>(
      render: (initialProps: Props) => Result,
      options?: Parameters<typeof actual.renderHook<Result, Props>>[1],
    ) =>
      actual.renderHook(render, {
        ...(options ?? {}),
        wrapper: withQueryClient(options?.wrapper as WrapperComponent | undefined),
      }),
  };
});

afterEach(async () => {
  const { cleanup } = await import("@testing-library/react");
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});
