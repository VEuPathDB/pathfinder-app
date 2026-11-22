// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import type { ParamSpec, Step } from "@strategist/shared";
import { saveDataset } from "@/lib/api/sites";
import { server } from "../../../../vitest.msw-setup";

const hoisted = vi.hoisted(() => ({
  footer: { current: null as null | { isSaving: boolean; onSave: () => void } },
  values: new Map<string, string>(),
  draft: null as null | Record<string, string>,
  mutateAsync: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@tanstack/react-form", () => ({
  useStore: () => Object.fromEntries(hoisted.values),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: hoisted.toastError } }));
vi.mock("./EditorBody", () => ({ EditorBody: () => null }));
vi.mock("./StepResults", () => ({ StepResults: () => null }));
vi.mock("./EditorFooter", () => ({
  EditorFooter: (props: { isSaving: boolean; onSave: () => void }) => {
    hoisted.footer.current = props;
    return null;
  },
}));

const VARIANT_FILTER: ParamSpec = {
  name: "variant_filter",
  displayName: "Variant filter",
  type: "filter",
  displayType: "",
  allowEmptyValue: true,
  isVisible: true,
  isNumber: false,
  countOnlyLeaves: false,
};

vi.mock("./useStepEditorState", () => ({
  useStepEditorState: () => ({
    kind: "search",
    name: "Genes by variants",
    setName: vi.fn(),
    paramSpecs: [VARIANT_FILTER],
    hiddenDefaults: {},
    operatorValue: "",
    setOperatorValue: vi.fn(),
    colocationParams: null,
    setColocationParams: vi.fn(),
    searchOptions: [],
    onDependentFieldChange: vi.fn(),
    form: {
      store: {},
      state: { values: {} },
      reset: vi.fn(),
      setFieldValue: (key: string, value: string) => {
        hoisted.values.set(key, value);
      },
    },
    paramFormHydrated: true,
  }),
}));
vi.mock("@/features/strategy/graph/StrategyGraphContext", () => ({
  useStrategyGraphCtx: () => ({ requestDelete: vi.fn() }),
}));
vi.mock("@/features/strategy/mutations", () => ({
  useDuplicateStepMutation: () => ({ mutate: vi.fn() }),
  useUpdateStepMutation: () => ({
    mutate: vi.fn(),
    mutateAsync: hoisted.mutateAsync,
    isPending: false,
    isError: false,
  }),
}));
vi.mock("@/features/strategy/mutations/useSaveSubstrategyMutation", () => ({
  useSaveSubstrategyMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/lib/api/strategy", () => ({ useStrategyData: () => null }));
vi.mock("@/state/strategy/useStepSnapshot", () => ({
  useStepSnapshot: () => ({ estimatedSize: null }),
}));
vi.mock("./hooks/useStepDraftPersistence", () => ({
  useStepDraftPersistence: () => ({
    scheduleWrite: vi.fn(),
    flush: vi.fn(),
    clear: vi.fn(),
  }),
  useRecoveredDraft: () => ({ draft: hoisted.draft, dismiss: vi.fn() }),
}));
vi.mock("./hooks/useStepDraftChanges", () => ({
  useStepDraftChanges: () => ({ hasChanges: true, changeCount: 1 }),
}));

import { EditorContent } from "./EditorContent";

const STEP: Step = {
  id: "step_7",
  kind: "search",
  displayName: "Genes by variants",
  searchName: "GenesByVariants",
  recordType: "gene",
  parameters: {},
};

function renderEditor(client: QueryClient, onClosed = vi.fn()) {
  let close: (() => Promise<void>) | null = null;
  const element = () => (
    <EditorContent
      step={STEP}
      siteId="plasmodb"
      recordType="gene"
      conversationId="conv-1"
      registerCloseHandler={(handler) => {
        close = handler;
      }}
      onClosed={onClosed}
    />
  );
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = render(element(), { wrapper });
  return {
    rerender: () => view.rerender(element()),
    close: async () => {
      if (close === null) throw new Error("no close handler registered");
      await close();
    },
  };
}

function holdDatasetSave(client: QueryClient): () => void {
  let release = () => {};
  server.use(
    http.post("*/api/v1/sites/plasmodb/datasets", async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return HttpResponse.json({ datasetId: "330713700" });
    }),
  );
  void client
    .getMutationCache()
    .build(client, {
      mutationKey: ["save-dataset", "plasmodb"],
      mutationFn: () =>
        saveDataset("plasmodb", {
          sourceType: "idList",
          sourceContent: { ids: ["PF3D7_0100100"] },
        }),
    })
    .execute(undefined);
  return () => release();
}

beforeEach(() => {
  hoisted.values.clear();
  hoisted.draft = null;
  hoisted.footer.current = null;
  hoisted.mutateAsync.mockReset();
  hoisted.toastError.mockReset();
});

afterEach(cleanup);

describe("EditorContent while a list is saved on the site", () => {
  it("holds the footer in its saving state", async () => {
    const client = new QueryClient();
    renderEditor(client);
    expect(hoisted.footer.current?.isSaving).toBe(false);

    const release = holdDatasetSave(client);

    await waitFor(() => expect(hoisted.footer.current?.isSaving).toBe(true));
    release();
    await waitFor(() => expect(hoisted.footer.current?.isSaving).toBe(false));
  });

  it("does not close or send the step", async () => {
    const client = new QueryClient();
    const onClosed = vi.fn();
    const editor = renderEditor(client, onClosed);
    const release = holdDatasetSave(client);
    await waitFor(() => expect(hoisted.footer.current?.isSaving).toBe(true));

    await act(editor.close);

    expect(onClosed).not.toHaveBeenCalled();
    expect(hoisted.mutateAsync).not.toHaveBeenCalled();
    release();
  });
});

describe("EditorContent with a value it cannot read", () => {
  it("says so when a restored filter draft is saved", async () => {
    hoisted.draft = { variant_filter: "[]" };
    const client = new QueryClient();
    const editor = renderEditor(client);
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    editor.rerender();

    act(() => hoisted.footer.current?.onSave());

    await waitFor(() =>
      expect(hoisted.toastError).toHaveBeenCalledWith(
        "The step could not be saved: Variant filter holds a value the editor cannot read",
      ),
    );
    expect(hoisted.mutateAsync).not.toHaveBeenCalled();
  });
});
