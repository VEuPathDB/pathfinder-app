/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import {
  QueryClientProvider,
  useSuspenseQuery,
  queryOptions,
} from "@tanstack/react-query";
import { createTestQueryClient } from "@/lib/query/testing";
import { QueryBoundary } from "../QueryBoundary";
import { DefaultSpinner } from "../DefaultSpinner";
import { DefaultQueryError } from "../DefaultQueryError";

function SuccessChild() {
  useSuspenseQuery(
    queryOptions({
      queryKey: ["test", "success"],
      queryFn: () => Promise.resolve("loaded"),
    }),
  );
  return <div>Success content</div>;
}

function FailChild() {
  useSuspenseQuery(
    queryOptions({
      queryKey: ["test", "fail"],
      queryFn: () => Promise.reject(new Error("Test query failed")),
      retry: false,
    }),
  );
  return <div>Should not render</div>;
}

afterEach(cleanup);

function renderWithClient(ui: React.ReactElement) {
  const queryClient = createTestQueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("DefaultSpinner", () => {
  it("renders a spinner", () => {
    const { container } = renderWithClient(<DefaultSpinner />);
    expect(container.querySelectorAll(".animate-spin")).toHaveLength(1);
  });
});

describe("DefaultQueryError", () => {
  it("renders error message and retry button", () => {
    const resetFn = vi.fn();
    renderWithClient(
      <DefaultQueryError
        error={new Error("Something broke")}
        resetErrorBoundary={resetFn}
      />,
    );
    expect(screen.getByText("Something broke")).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });
});

describe("QueryBoundary", () => {
  it("renders children after query resolves", async () => {
    renderWithClient(
      <QueryBoundary>
        <SuccessChild />
      </QueryBoundary>,
    );
    await waitFor(() => {
      expect(screen.getByText("Success content")).toBeTruthy();
    });
  });

  it("shows loading fallback while query is pending", () => {
    const queryClient = createTestQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <QueryBoundary loadingFallback={<div>Custom loading</div>}>
          <SuccessChild />
        </QueryBoundary>
      </QueryClientProvider>,
    );
    expect(screen.getByText("Custom loading")).toBeTruthy();
  });

  it("shows error fallback when query fails", async () => {
    renderWithClient(
      <QueryBoundary>
        <FailChild />
      </QueryBoundary>,
    );
    await waitFor(() => {
      expect(screen.getByText("Test query failed")).toBeTruthy();
      expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
    });
  });
});
