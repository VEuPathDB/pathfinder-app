/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { AuditRunSummary } from "@pathfinder/shared/generated/types/AuditRunSummary";
import { listAuditRunsSuspenseQueryOptions } from "@pathfinder/shared/generated/hooks/useListAuditRunsSuspense";

import { auditWordsOptions } from "@/lib/api/audits";
import { createTestWrapper } from "@/lib/query/testing";

import served from "../../../../../packages/spec/audit_words.json";
import { server } from "../../../vitest.msw-setup";
import { SAMPLE_RUN, SAMPLE_RUN_ID } from "./__fixtures__/sampleRun";
import { AuditRunsPage } from "./AuditRunsPage";

const RUNS_URL = "http://localhost:3000/pathfinder/api/v1/audits";
const WORDS_URL = "http://localhost:3000/pathfinder/api/v1/audits/words";

const SAMPLE_CHECKS =
  "Gene length against orthologs; Exon structure against RNA-seq; Organelle genes at the circular join; Pseudogene calls on intact genes; Strain model against its reference";

const HALTED: AuditRunSummary = {
  ...SAMPLE_RUN.run,
  id: "00000000-0000-4000-8000-000000000009",
  siteId: "toxodb",
  phase: "halted",
  genomes: ["Toxoplasma gondii ME49"],
  checks: ["gene_split", "selenoprotein_end"],
  targets: 0,
  createdAt: "2026-10-23T09:00:00Z",
};

function cells(row: HTMLElement): (string | null)[] {
  return within(row)
    .getAllByRole("cell")
    .map((cell) => cell.textContent);
}

function bodyRows(): HTMLElement[] {
  return within(screen.getByRole("table")).getAllByRole("row").slice(1);
}

function renderWith(runs: AuditRunSummary[]) {
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(
    listAuditRunsSuspenseQueryOptions({ siteId: null }).queryKey,
    runs,
  );
  queryClient.setQueryData(auditWordsOptions().queryKey, served);
  return render(<AuditRunsPage lockedSite={null} />, { wrapper: Wrapper });
}

function serveRuns(runs: AuditRunSummary[]): string[] {
  const asked: string[] = [];
  server.use(
    http.get(WORDS_URL, () => HttpResponse.json(served)),
    http.get(RUNS_URL, ({ request }) => {
      asked.push(request.url);
      const site = new URL(request.url).searchParams.get("siteId");
      return HttpResponse.json(
        runs.filter((run) => site === null || run.siteId === site),
      );
    }),
  );
  return asked;
}

function renderServed(lockedSite: string | null) {
  const { Wrapper } = createTestWrapper();
  return render(<AuditRunsPage lockedSite={lockedSite} />, { wrapper: Wrapper });
}

describe("AuditRunsPage", () => {
  it("lists each audit with its site, scope, checks and status, linked to its page", () => {
    renderWith([SAMPLE_RUN.run]);
    const link = screen.getByRole("link", {
      name: "Open the audit of Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets, started Oct 22, 2026",
    });
    expect(link).toHaveAttribute("href", `/audits/${SAMPLE_RUN_ID}`);
    expect(link).toHaveTextContent("Oct 22, 2026");
    const row = screen.getByRole("row", { name: /Plasmodium falciparum Dd2/ });
    expect(cells(row)).toEqual([
      "Oct 22, 2026",
      "PlasmoDB",
      "Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets",
      SAMPLE_CHECKS,
      "Finished",
    ]);
    expect(
      screen.getByRole("table", { name: "Your audits, newest first" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("columnheader").map((header) => header.textContent),
    ).toEqual(["Started", "Site", "What it examines", "Checks", "Status"]);
  });

  it("keeps the order the API lists the audits in", () => {
    renderWith([HALTED, SAMPLE_RUN.run]);
    expect(bodyRows().map(cells)).toEqual([
      [
        "Oct 23, 2026",
        "ToxoDB",
        "Toxoplasma gondii ME49",
        "One gene split into two models; Selenoproteins cut at their selenocysteine",
        "Stopped",
      ],
      [
        "Oct 22, 2026",
        "PlasmoDB",
        "Plasmodium falciparum NF54, Plasmodium falciparum Dd2 and 3 gene targets",
        SAMPLE_CHECKS,
        "Finished",
      ],
    ]);
    expect(
      screen.getByRole("link", {
        name: "Open the audit of Toxoplasma gondii ME49, started Oct 23, 2026",
      }),
    ).toHaveAttribute("href", "/audits/00000000-0000-4000-8000-000000000009");
  });

  it("says how to start one when there is none", () => {
    renderWith([]);
    expect(
      screen.getByText(
        "No audits yet. Ask the audit assistant in a conversation to audit a genome.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("lists every site's audits on the portal", async () => {
    const asked = serveRuns([HALTED, SAMPLE_RUN.run]);
    renderServed(null);
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(bodyRows().map((row) => cells(row)[1])).toEqual(["ToxoDB", "PlasmoDB"]);
    expect(asked).toEqual([RUNS_URL]);
  });

  it("lists only the locked site's audits, with no site column", async () => {
    const asked = serveRuns([HALTED, SAMPLE_RUN.run]);
    renderServed("toxodb");
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(asked).toEqual([`${RUNS_URL}?siteId=toxodb`]);
    expect(bodyRows().map(cells)).toEqual([
      [
        "Oct 23, 2026",
        "Toxoplasma gondii ME49",
        "One gene split into two models; Selenoproteins cut at their selenocysteine",
        "Stopped",
      ],
    ]);
    expect(
      screen.getAllByRole("columnheader").map((header) => header.textContent),
    ).toEqual(["Started", "What it examines", "Checks", "Status"]);
  });

  it("says the locked site has no audits yet", async () => {
    const asked = serveRuns([SAMPLE_RUN.run]);
    renderServed("toxodb");
    expect(
      await screen.findByText(
        "No audits on ToxoDB yet. Ask the audit assistant in a conversation to audit a genome.",
      ),
    ).toBeInTheDocument();
    expect(asked).toEqual([`${RUNS_URL}?siteId=toxodb`]);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows the spinner while the audits load", () => {
    server.use(
      http.get(WORDS_URL, () => HttpResponse.json(served)),
      http.get(RUNS_URL, () => new Promise<never>(() => undefined)),
    );
    const { container } = renderServed(null);
    expect(container.querySelectorAll(".animate-spin")).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "Audits" })).toBeNull();
  });

  it("shows the query error when the audits cannot be read", async () => {
    server.use(
      http.get(WORDS_URL, () => HttpResponse.json(served)),
      http.get(RUNS_URL, () =>
        HttpResponse.json(
          { title: "Audits unavailable", status: 500 },
          { status: 500 },
        ),
      ),
    );
    renderServed(null);
    expect(await screen.findByText("Audits unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows the query error when the audit words cannot be read", async () => {
    server.use(
      http.get(WORDS_URL, () =>
        HttpResponse.json({ title: "Words unavailable", status: 500 }, { status: 500 }),
      ),
      http.get(RUNS_URL, () => HttpResponse.json([SAMPLE_RUN.run])),
    );
    renderServed(null);
    expect(await screen.findByText("Words unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
