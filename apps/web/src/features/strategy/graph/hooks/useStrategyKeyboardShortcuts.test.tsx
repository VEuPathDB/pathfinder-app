// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Step, Strategy } from "@pathfinder/shared";

const fitViewMock = vi.fn();
const zoomInMock = vi.fn();
const zoomOutMock = vi.fn();
const pushMock = vi.fn();
const addStepMutateMock = vi.fn();
let requestDeleteMock = vi.fn();
let requestDeleteManyMock = vi.fn();

vi.mock("@xyflow/react", () => ({
  useReactFlow: () => ({
    fitView: fitViewMock,
    zoomIn: zoomInMock,
    zoomOut: zoomOutMock,
  }),
}));

let pathnameMock = "/plasmodb/conversation/strat-1/strategy";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
  useParams: () => ({ siteId: "plasmodb" }),
  usePathname: () => pathnameMock,
}));

vi.mock("@/features/strategy/mutations", () => ({
  useAddStepMutation: () => ({ mutate: addStepMutateMock }),
}));

import { StrategyGraphProvider } from "@/features/strategy/graph/StrategyGraphContext";
import { chatUrl, strategyCanvasUrl } from "@/lib/routes";
import { useStrategyKeyboardShortcuts } from "./useStrategyKeyboardShortcuts";

function makeStep(id: string, extras: Partial<Step> = {}): Step {
  return {
    id,
    kind: "search",
    displayName: id,
    searchName: `search-${id}`,
    parameters: {},
    ...extras,
  };
}

function makeStrategy(steps: Step[]): Strategy {
  return {
    id: "strat-1",
    name: "Test",
    rootStepId: steps.at(-1)?.id ?? steps[0]?.id ?? "",
    recordType: "gene",
    steps,
    siteId: "plasmodb",
    isSaved: false,
    createdAt: "2026-01-01T00:00:00.000Z",
    updatedAt: "2026-01-01T00:00:00.000Z",
  };
}

interface CtxOverrides {
  selectedNodeIds?: string[];
  selectedStep?: Step | null;
  setSelectedStep?: (step: Step | null) => void;
  handleRelayout?: () => void;
  handleStartCombineFromSelection?: () => void;
  setOrthologModalOpen?: (open: boolean) => void;
  editableSteps?: Step[];
  strategy?: Strategy | null;
}

function makeWrapper(overrides: CtxOverrides = {}) {
  const steps = overrides.editableSteps ?? [makeStep("a"), makeStep("b")];
  const strategy = overrides.strategy ?? makeStrategy(steps);
  const value = {
    isCompact: false,
    nodes: [],
    edges: [],
    selectedStep: overrides.selectedStep ?? null,
    setSelectedStep: overrides.setSelectedStep ?? vi.fn(),
    edgeMenu: null,
    setEdgeMenu: vi.fn(),
    orthologTargetId: null,
    setOrthologModalOpen: overrides.setOrthologModalOpen ?? vi.fn(),
    syncStatus: "idle" as const,
    selectedNodeIds: overrides.selectedNodeIds ?? [],
    handleSelectionChange: vi.fn(),
    isValidConnection: () => true,
    handleConnect: vi.fn(),
    handleDeleteEdge: vi.fn(),
    onNodesChange: vi.fn(),
    onEdgesChange: vi.fn(),
    handleNodesDelete: vi.fn(),
    handleNodeDragStop: vi.fn(),
    handleStartCombineFromSelection:
      overrides.handleStartCombineFromSelection ?? vi.fn(),
    handleStartOrthologTransformFromSelection: vi.fn(),
    handleOrthologChoose: vi.fn(),
    handleRelayout: overrides.handleRelayout ?? vi.fn(),
    handleMoveStart: vi.fn(),
    editableSteps: steps,
    combineMismatchGroups: [],
    draftStrategy: null,
    updateStep: vi.fn(),
    requestDelete: requestDeleteMock,
    requestDeleteMany: requestDeleteManyMock,
    deleteDialogProps: null,
    strategy,
    siteId: "plasmodb",
  };
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StrategyGraphProvider value={value as never}>{children}</StrategyGraphProvider>
    );
  };
}

interface RenderArgs {
  overrides?: CtxOverrides;
  onOpenQuickSwitcher?: () => void;
  onToggleShortcutsOverlay?: () => void;
}

function renderShortcuts(args: RenderArgs = {}) {
  const onOpenQuickSwitcher = args.onOpenQuickSwitcher ?? vi.fn();
  const onToggleShortcutsOverlay = args.onToggleShortcutsOverlay ?? vi.fn();
  const Wrapper = makeWrapper(args.overrides);
  const result = renderHook(
    () =>
      useStrategyKeyboardShortcuts({
        onOpenQuickSwitcher,
        onToggleShortcutsOverlay,
      }),
    { wrapper: Wrapper },
  );
  return { ...result, onOpenQuickSwitcher, onToggleShortcutsOverlay };
}

describe("useStrategyKeyboardShortcuts", () => {
  afterEach(() => {
    cleanup();
    fitViewMock.mockReset();
    zoomInMock.mockReset();
    zoomOutMock.mockReset();
    pushMock.mockReset();
    requestDeleteMock = vi.fn();
    requestDeleteManyMock = vi.fn();
    addStepMutateMock.mockReset();
  });

  it("r calls relayout", () => {
    const handleRelayout = vi.fn();
    renderShortcuts({ overrides: { handleRelayout } });
    fireEvent.keyDown(document, { key: "r" });
    expect(handleRelayout).toHaveBeenCalled();
  });

  it("f calls fitView", () => {
    renderShortcuts();
    fireEvent.keyDown(document, { key: "f" });
    expect(fitViewMock).toHaveBeenCalled();
  });

  it("e opens editor for selected step", () => {
    const setSelectedStep = vi.fn();
    const step = makeStep("focused");
    renderShortcuts({
      overrides: {
        selectedNodeIds: ["focused"],
        editableSteps: [step],
        setSelectedStep,
      },
    });
    fireEvent.keyDown(document, { key: "e" });
    expect(setSelectedStep).toHaveBeenCalledWith(step);
  });

  it("Backspace fires requestDelete for the selected step", () => {
    renderShortcuts({ overrides: { selectedNodeIds: ["doomed"] } });
    fireEvent.keyDown(document, { key: "Backspace" });
    expect(requestDeleteMock).toHaveBeenCalledWith("doomed");
  });

  it("Backspace fires requestDeleteMany when multiple steps selected", () => {
    renderShortcuts({ overrides: { selectedNodeIds: ["a", "b"] } });
    fireEvent.keyDown(document, { key: "Backspace" });
    expect(requestDeleteManyMock).toHaveBeenCalledWith(["a", "b"]);
  });

  it("skips when target is an input", () => {
    const handleRelayout = vi.fn();
    renderShortcuts({ overrides: { handleRelayout } });
    const input = document.createElement("input");
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: "r" });
    expect(handleRelayout).not.toHaveBeenCalled();
    input.remove();
  });

  it("g s sequence navigates to strategy route", () => {
    renderShortcuts();
    fireEvent.keyDown(document, { key: "g" });
    fireEvent.keyDown(document, { key: "s" });
    expect(pushMock).toHaveBeenCalledWith(strategyCanvasUrl("plasmodb", "strat-1"));
  });

  it("g c sequence navigates to chat route", () => {
    renderShortcuts();
    fireEvent.keyDown(document, { key: "g" });
    fireEvent.keyDown(document, { key: "c" });
    expect(pushMock).toHaveBeenCalledWith(chatUrl("plasmodb", "strat-1"));
  });

  it("Cmd+K invokes onOpenQuickSwitcher", () => {
    const onOpenQuickSwitcher = vi.fn();
    renderShortcuts({ onOpenQuickSwitcher });
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(onOpenQuickSwitcher).toHaveBeenCalled();
  });

  it("? toggles shortcuts overlay", () => {
    const onToggleShortcutsOverlay = vi.fn();
    renderShortcuts({ onToggleShortcutsOverlay });
    fireEvent.keyDown(document, { key: "?" });
    expect(onToggleShortcutsOverlay).toHaveBeenCalled();
  });

  it("Esc closes editor sheet (step route) back to the canvas", () => {
    const setSelectedStep = vi.fn();
    pathnameMock = "/plasmodb/conversation/strat-1/strategy/step/open";
    renderShortcuts({
      overrides: { selectedStep: makeStep("open"), setSelectedStep },
    });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(setSelectedStep).toHaveBeenCalledWith(null);
    expect(pushMock).toHaveBeenCalledWith(strategyCanvasUrl("plasmodb", "strat-1"));
    pathnameMock = "/plasmodb/conversation/strat-1/strategy";
  });

  it("c fires combine selection handler when ≥2 selected", () => {
    const handleStartCombineFromSelection = vi.fn();
    renderShortcuts({
      overrides: {
        selectedNodeIds: ["a", "b"],
        handleStartCombineFromSelection,
      },
    });
    fireEvent.keyDown(document, { key: "c" });
    expect(handleStartCombineFromSelection).toHaveBeenCalled();
  });

  it("g leader times out after 1s", () => {
    vi.useFakeTimers();
    try {
      renderShortcuts();
      fireEvent.keyDown(document, { key: "g" });
      act(() => {
        vi.advanceTimersByTime(1100);
      });
      fireEvent.keyDown(document, { key: "s" });
      expect(pushMock).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});
