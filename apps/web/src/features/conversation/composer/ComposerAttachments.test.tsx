/**
 * @vitest-environment jsdom
 */
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import type { ModelCatalogEntry } from "@pathfinder/shared";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useChatRuntime } from "@/features/conversation/runtime/useChatRuntime";
import { useSettingsStore } from "@/state/useSettingsStore";

import { server } from "../../../../vitest.msw-setup";
import { AttachButton, ComposerAttachmentList } from "./ComposerAttachments";

function model(name: string, reads: boolean): ModelCatalogEntry {
  return {
    id: `openai:${name}`,
    name,
    modelName: name,
    provider: "openai",
    enabled: true,
    supportsImages: reads,
    supportsDocuments: reads,
  };
}

const TEXT_ONLY = model("text-only", false);
const READER = model("reader", true);

const GENE_ID_ACCEPT = ".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain";
const READER_ACCEPT = `${GENE_ID_ACCEPT},image/png,image/jpeg,image/webp,image/gif,application/pdf`;

function ChatComposer() {
  const { runtime } = useChatRuntime({
    conversationId: "33333333-4444-4555-8666-777777777777",
    assistantId: "pathfinder",
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ComposerAttachmentList assistantId="pathfinder" refusal={null} />
      <AttachButton assistantId="pathfinder" />
    </AssistantRuntimeProvider>
  );
}

/** The accept list of every file chooser the page opens, in order. */
function recordChoosers(): string[] {
  const opened: string[] = [];
  vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(function (
    this: HTMLInputElement,
  ) {
    opened.push(this.accept);
  });
  return opened;
}

afterEach(() => {
  useSettingsStore.getState().resetToDefaults();
  vi.restoreAllMocks();
});

function serveCatalog(): void {
  server.use(
    http.get("http://localhost:3000/api/v1/models", () =>
      HttpResponse.json({
        models: [TEXT_ONLY, READER],
        defaultProvider: "openai",
        defaultTier: "default",
        phaseDefaults: { lead: TEXT_ONLY.id },
      }),
    ),
  );
}

describe("AttachButton", () => {
  it("opens a chooser for the kinds the current reading model reads", async () => {
    serveCatalog();
    const opened = recordChoosers();
    render(<ChatComposer />);
    const button = await screen.findByRole("button", {
      name: "Attach a gene-ID list",
    });
    fireEvent.click(button);

    act(() => {
      useSettingsStore.getState().setPhaseModel("lead", READER.id);
    });
    await waitFor(() => {
      expect(button).toHaveAccessibleName("Attach a gene-ID list, an image or a PDF");
    });
    fireEvent.click(button);

    expect(opened).toEqual([GENE_ID_ACCEPT, READER_ACCEPT]);
  });

  it("adds the file the chooser returns to the composer", async () => {
    serveCatalog();
    const { container } = render(<ChatComposer />);
    const chooser = container.querySelector<HTMLInputElement>('input[type="file"]');
    if (chooser === null) throw new Error("the Attach button renders no file chooser");
    const genes = new File(["PF3D7_0100100\n"], "genes.csv", { type: "text/csv" });

    fireEvent.change(chooser, { target: { files: [genes] } });

    expect(await screen.findByText("genes.csv")).toBeInTheDocument();
  });
});
