import type * as TestingLibraryReact from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { afterEach, vi } from "vitest";

// A file in the node environment renders nothing, so it loads none of the DOM
// setup. A page file loads it here, before its own mocks can replace a module.
const inPage = typeof window !== "undefined";

type WrapperComponent = ComponentType<{ children: ReactNode }>;

async function queryClientWrapper(): Promise<
  (Wrapper?: WrapperComponent) => WrapperComponent
> {
  const [{ createElement }, { QueryClientProvider }, { createTestQueryClient }] =
    await Promise.all([
      import("react"),
      import("@tanstack/react-query"),
      import("./src/lib/query/testing"),
      import("@testing-library/jest-dom/vitest"),
    ]);
  return (Wrapper) => {
    const queryClient = createTestQueryClient();

    function QueryClientWrapper({ children }: { children: ReactNode }) {
      return createElement(
        QueryClientProvider,
        { client: queryClient },
        Wrapper ? createElement(Wrapper, null, children) : children,
      );
    }

    return QueryClientWrapper;
  };
}

const withQueryClient = inPage ? await queryClientWrapper() : undefined;

vi.mock("@testing-library/react", async () => {
  const actual = await vi.importActual<typeof TestingLibraryReact>(
    "@testing-library/react",
  );
  if (withQueryClient === undefined) {
    throw new Error("Testing Library renders only in the jsdom environment");
  }

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
  if (inPage) {
    const { cleanup } = await import("@testing-library/react");
    cleanup();
  }
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

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
