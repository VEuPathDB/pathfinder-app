/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { SiteResponse } from "@strategist/shared";

import { sitesOptions } from "@/lib/api/sites";
import type { TraceRowStatus } from "@veupathdb/assistant-client";

import { RUN, SAMPLE_RUN } from "../__fixtures__/auditReads";
import { TraceRow } from "./TraceRow";
import type { TraceRowView } from "./traceTypes";

function row(patch: Partial<TraceRowView>): TraceRowView {
  return {
    key: "call_1",
    toolCallId: "call_1",
    toolName: "preview_eda_subset",
    summary: "6 of 12 Sample",
    status: "ok",
    input: { entityId: "ENT_8151325d" },
    output: { count: 6 },
    errorText: null,
    ...patch,
  };
}

const TOXODB: SiteResponse = {
  id: "toxodb",
  name: "ToxoDB",
  displayName: "ToxoDB (Toxoplasma)",
  baseUrl: "https://qa.toxodb.org/toxo.qa/service",
  projectId: "ToxoDB",
  isPortal: false,
  siteOrigin: "https://qa.toxodb.org",
  signInUrl: "https://qa.toxodb.org/toxo.qa/app/user/login",
  pageUrl: "https://qa.toxodb.org/toxo.qa/app/pathfinder",
  available: true,
  unavailableReason: null,
  offersAudits: false,
};

function label(name: string): string {
  return name === "preview_eda_subset" ? "Preview samples" : name;
}

const GLYPHS: readonly (readonly [TraceRowStatus, string])[] = [
  ["running", "animate-spin"],
  ["ok", "text-success"],
  ["empty", "text-warning"],
  ["warn", "text-warning"],
  ["error", "text-destructive"],
  ["corrected", "text-muted-foreground"],
  ["denied", "text-muted-foreground"],
  ["awaiting-approval", "text-warning"],
  ["stopped", "text-muted-foreground"],
];

describe("TraceRow", () => {
  it.each(GLYPHS)("draws the %s status with its own glyph class", (status, css) => {
    render(<TraceRow row={row({ status })} showRaw={false} nameFor={label} />);
    expect(screen.getByTestId("trace-row-status")).toHaveClass(css);
    expect(screen.getByTestId("trace-row")).toHaveTextContent("Preview samples");
  });

  it.each(GLYPHS)("names the %s status on the glyph", (status) => {
    render(<TraceRow row={row({ status })} showRaw={false} nameFor={label} />);
    expect(screen.getByTestId("trace-row-status")).toHaveAttribute(
      "data-status",
      status,
    );
  });

  it("gives every status a glyph of its own", () => {
    const seen = GLYPHS.map(([status]) => {
      render(<TraceRow row={row({ status })} showRaw={false} nameFor={label} />);
      const glyph = screen.getAllByTestId("trace-row-status").at(-1);
      return glyph?.getAttribute("class") ?? "";
    });
    expect(new Set(seen).size).toBe(GLYPHS.length);
  });

  it("draws a call its turn left open with a still glyph", () => {
    render(
      <TraceRow row={row({ status: "stopped" })} showRaw={false} nameFor={label} />,
    );
    expect(screen.getByTestId("trace-row-status")).not.toHaveClass("animate-spin");
  });

  it("reads the word its turn left the call with, when the call wrote none", () => {
    render(
      <TraceRow
        row={row({ status: "stopped", summary: null })}
        showRaw={false}
        nameFor={label}
        stoppedLabel="Stopped"
      />,
    );
    expect(screen.getByTestId("trace-row-summary")).toHaveTextContent("Stopped");
  });

  it("reads the verb and the tool's own summary", () => {
    render(<TraceRow row={row({})} showRaw={false} nameFor={label} />);
    const line = screen.getByTestId("trace-row");
    expect(line).toHaveTextContent("Preview samples");
    expect(within(line).getByTestId("trace-row-summary")).toHaveTextContent(
      "6 of 12 Sample",
    );
  });

  it("draws no summary element for a call that wrote no line", () => {
    render(<TraceRow row={row({ summary: null })} showRaw={false} nameFor={label} />);
    expect(screen.queryAllByTestId("trace-row-summary")).toHaveLength(0);
  });

  it("draws no summary element for a line that came through empty", () => {
    render(<TraceRow row={row({ summary: "" })} showRaw={false} nameFor={label} />);
    expect(screen.queryAllByTestId("trace-row-summary")).toHaveLength(0);
    expect(screen.getByTestId("trace-row")).toHaveTextContent("Preview samples");
  });

  it("reads the error text in place of the summary when the call failed", () => {
    render(
      <TraceRow
        row={row({
          status: "error",
          summary: null,
          errorText: "WDK rejected the search",
        })}
        showRaw={false}
        nameFor={label}
      />,
    );
    expect(screen.getByTestId("trace-row-summary")).toHaveTextContent(
      "WDK rejected the search",
    );
  });

  it("reads why a corrected call was handed back, in place of its summary", () => {
    render(
      <TraceRow
        row={row({
          status: "corrected",
          summary: null,
          errorText: "dataset records cannot be counted by genome_assembly",
        })}
        showRaw={false}
        nameFor={label}
      />,
    );
    expect(screen.getByTestId("trace-row-summary")).toHaveTextContent(
      "dataset records cannot be counted by genome_assembly",
    );
    expect(screen.getByTestId("trace-row-status")).not.toHaveClass("text-destructive");
  });

  it("clips a long error to a word boundary and ends it in three periods", () => {
    const long = "alpha ".repeat(40).trim();
    render(
      <TraceRow
        row={row({ status: "error", summary: null, errorText: long })}
        showRaw={false}
        nameFor={label}
      />,
    );
    const text = screen.getByTestId("trace-row-summary").textContent;
    expect(text).toBe(`${"alpha ".repeat(20).trim()}...`);
    expect(text.length).toBe(122);
  });

  it("shows no raw block and no JSON at all with the dev flag off", () => {
    const view = render(<TraceRow row={row({})} showRaw={false} nameFor={label} />);
    expect(view.queryAllByTestId("trace-row-raw")).toHaveLength(0);
    expect(view.container.textContent).not.toContain("{");
    expect(view.container.textContent).not.toContain("entityId");
  });

  it("reveals the call's own input and output with the dev flag on", async () => {
    const view = render(<TraceRow row={row({})} showRaw nameFor={label} />);
    expect(view.getAllByTestId("trace-row-raw")).toHaveLength(1);
    const raw = view.getByTestId("trace-row-raw");
    expect(raw).toHaveTextContent("entityId");
    expect(raw).toHaveTextContent("ENT_8151325d");
    expect(raw).toHaveTextContent("count");
  });

  it("opens the related experiments of other sites under the row", async () => {
    const searched = row({
      toolName: "search_for_searches",
      summary:
        "12 searches on PlasmoDB; related experiments on 1 other site (for reference)",
      output: [
        { name: "GenesByText" },
        {
          otherSites: {
            note: "Experiments on other VEuPathDB sites.",
            experiments: [
              {
                site: "toxodb",
                datasetId: "DS_0a1b2c",
                similarity: 0.71,
                line: "Heat shock time course in tachyzoites (RNA-Seq)",
              },
              {
                site: "cryptodb",
                datasetId: "DS_9f8e7d",
                similarity: 0.64,
                line: "Oocyst stress response (microarray)",
              },
            ],
          },
        },
      ],
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(sitesOptions().queryKey, [TOXODB]);
    render(
      <QueryClientProvider client={client}>
        <TraceRow row={searched} showRaw={false} nameFor={label} />
      </QueryClientProvider>,
    );

    const toggle = screen.getByRole("button", { name: "Related experiments" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryAllByTestId("trace-row-other-sites")).toHaveLength(0);

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const items = within(screen.getByTestId("trace-row-other-sites")).getAllByRole(
      "listitem",
    );
    expect(items.map((item) => item.textContent)).toEqual([
      "Heat shock time course in tachyzoites (RNA-Seq)ToxoDB (Toxoplasma)",
      "Oocyst stress response (microarray)cryptodb",
    ]);
    expect(
      within(items[0] ?? document.body).getByRole("link", {
        name: "Heat shock time course in tachyzoites (RNA-Seq)",
      }),
    ).toHaveAttribute(
      "href",
      "https://qa.toxodb.org/toxo.qa/app/record/dataset/DS_0a1b2c",
    );
    expect(within(items[1] ?? document.body).queryAllByRole("link")).toHaveLength(0);

    await userEvent.click(toggle);
    expect(screen.queryAllByTestId("trace-row-other-sites")).toHaveLength(0);
  });

  it("offers no related experiments on a row whose output names none", () => {
    render(<TraceRow row={row({})} showRaw={false} nameFor={label} />);
    expect(
      screen.queryAllByRole("button", { name: "Related experiments" }),
    ).toHaveLength(0);
  });

  it("links an audit read to its report", () => {
    render(
      <TraceRow
        row={row({
          toolName: "read_audit_run",
          summary: "Audit run finished",
          input: { run_id: RUN },
          output: { answer: SAMPLE_RUN },
        })}
        showRaw={false}
        nameFor={label}
      />,
    );
    expect(screen.getByRole("link", { name: "Open the audit report" })).toHaveAttribute(
      "href",
      `/audits/${RUN}`,
    );
  });

  it("draws no report link on a row that is not an audit read", () => {
    render(<TraceRow row={row({})} showRaw={false} nameFor={label} />);
    expect(screen.queryAllByRole("link")).toEqual([]);
  });

  it("keeps the tool call part testid the thread has always carried", () => {
    render(<TraceRow row={row({})} showRaw={false} nameFor={label} />);
    const part = screen.getByTestId("tool-call-part");
    expect(part.querySelectorAll('[data-testid="trace-row"]')).toHaveLength(1);
  });

  it("marks the think tool's row with its own testid", () => {
    render(
      <TraceRow
        row={row({ toolName: "think", summary: "weighing two searches" })}
        showRaw={false}
        nameFor={label}
      />,
    );
    const part = screen.getByTestId("tool-think");
    expect(part.querySelectorAll('[data-testid="trace-row"]')).toHaveLength(1);
    expect(screen.queryAllByTestId("tool-call-part")).toHaveLength(0);
  });
});
