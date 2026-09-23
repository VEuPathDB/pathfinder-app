/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { use } from "react";
import { createTestWrapper } from "@/lib/query/testing";

const mockSystemReady = vi.hoisted(() => vi.fn());
const reloadPage = vi.hoisted(() => vi.fn());
vi.mock("./reloadPage", () => ({ reloadPage }));

vi.mock("@pathfinder/shared/generated/hooks/useSystemReady", () => ({
  systemReady: mockSystemReady,
  systemReadyQueryKey: () => [{ url: "/health/system" }] as const,
  systemReadyQueryOptions: () => ({
    queryKey: [{ url: "/health/system" }] as const,
    queryFn: mockSystemReady,
  }),
}));

const READY = { ready: true, apiReady: true, workerAlive: true, notReady: [] };

async function renderGate(
  children: React.ReactNode = <div data-testid="app-content">ready content</div>,
) {
  const { SystemReadyGate } = await import("./SystemReadyGate");
  const { Wrapper } = createTestWrapper();
  return render(
    <Wrapper>
      <SystemReadyGate siteId="plasmodb">{children}</SystemReadyGate>
    </Wrapper>,
  );
}

/** A fetch that records each request and never answers. */
function recordingFetch(requested: string[]) {
  return vi.fn((input: string) => {
    const url = new URL(input);
    requested.push(`${url.pathname}${url.search}`);
    return new Promise<Response>(() => {});
  });
}

const appCodeNeverArrives = new Promise<never>(() => {});

function StillLoadingAppCode(): React.ReactNode {
  return use(appCodeNeverArrives);
}

describe("SystemReadyGate", () => {
  beforeEach(() => {
    vi.resetModules();
    mockSystemReady.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("requests the sites, the models and the sign-in status before the app renders", async () => {
    mockSystemReady.mockResolvedValue(READY);
    const requested: string[] = [];
    vi.stubGlobal("fetch", recordingFetch(requested));
    const seenByApp: string[][] = [];
    function App() {
      seenByApp.push([...requested]);
      return <div data-testid="app-content" />;
    }

    await renderGate(<App />);

    await waitFor(() => {
      expect(screen.getByTestId("app-content")).toBeInTheDocument();
    });
    expect(seenByApp[0]).toEqual(
      expect.arrayContaining([
        "/api/v1/sites",
        "/api/v1/models",
        "/api/v1/veupathdb/auth/status?siteId=plasmodb",
      ]),
    );
  });

  it("shows the loading screen while the app code loads and offers a reload after 20 s", async () => {
    vi.useFakeTimers();
    mockSystemReady.mockResolvedValue(READY);
    vi.stubGlobal("fetch", recordingFetch([]));

    await renderGate(<StillLoadingAppCode />);
    await act(() => vi.advanceTimersByTimeAsync(0));

    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByText(/starting up/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reload" })).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(20_000));
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));

    expect(reloadPage).toHaveBeenCalledTimes(1);
  });

  it("shows the startup screen while not ready, listing what is pending", async () => {
    mockSystemReady.mockResolvedValue({
      ready: false,
      apiReady: false,
      workerAlive: false,
      notReady: ["database"],
    });

    await renderGate();

    await waitFor(() => {
      expect(screen.getByText(/starting up/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/database/)).toBeInTheDocument();
    expect(screen.queryByTestId("app-content")).not.toBeInTheDocument();
  });

  it("renders the app behind a banner when only the worker is unresponsive", async () => {
    mockSystemReady.mockResolvedValue({
      ready: false,
      apiReady: true,
      workerAlive: false,
      notReady: ["worker"],
    });

    await renderGate();

    await waitFor(() => {
      expect(screen.getByTestId("app-content")).toBeInTheDocument();
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      /background service is not responding/i,
    );
    expect(screen.queryByText(/failed to start/i)).not.toBeInTheDocument();
  });

  it("keeps the fatal screen when a subsystem other than the worker is down", async () => {
    mockSystemReady.mockResolvedValue({
      ready: false,
      apiReady: false,
      workerAlive: true,
      notReady: ["database"],
    });

    await renderGate();

    await waitFor(() => {
      expect(screen.getByText(/starting up/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("app-content")).not.toBeInTheDocument();
  });

  it("renders children once the system is ready", async () => {
    mockSystemReady.mockResolvedValue({
      ready: true,
      apiReady: true,
      workerAlive: true,
      notReady: [],
    });

    await renderGate();

    await waitFor(() => {
      expect(screen.getByTestId("app-content")).toBeInTheDocument();
    });
    expect(screen.queryByText(/starting up/i)).not.toBeInTheDocument();
  });
});
