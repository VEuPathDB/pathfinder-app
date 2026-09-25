/**
 * @vitest-environment jsdom
 */
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { useSessionStore } from "@/state/useSessionStore";

import { ChatEmptyState } from "./ChatEmptyState";

function EmptyThread({ children }: { children: ReactNode }) {
  const runtime = useLocalRuntime({
    async run() {
      return { content: [] };
    },
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
  );
}

describe("ChatEmptyState", () => {
  beforeEach(() => {
    useSessionStore.getState().setSelectedSite("plasmodb");
  });

  it("names the site by its short name in the strategy builder's sentence", () => {
    render(
      <EmptyThread>
        <ChatEmptyState assistantId="pathfinder" />
      </EmptyThread>,
    );

    expect(screen.getByTestId("chat-empty-blurb").textContent).toBe(
      "Build and refine multi-step PlasmoDB search strategies with guided " +
        "parameter selection and validation.",
    );
  });
});
