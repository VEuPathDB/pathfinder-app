/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { SiteResponse } from "@pathfinder/shared";

vi.mock("next/navigation", () => ({ usePathname: () => "/audits" }));

import { sitesOptions } from "@/lib/api/sites";
import { createTestWrapper } from "@/lib/query/testing";

import served from "../../../../../../packages/spec/audit_words.json";
import { server } from "../../../../vitest.msw-setup";
import Page from "./page";

const RUNS_URL = "http://localhost:3000/pathfinder/api/v1/audits";

function site(id: string, origin: string, isPortal = false): SiteResponse {
  return {
    id,
    name: id,
    displayName: id,
    baseUrl: `${origin}/${id}/service`,
    projectId: id,
    isPortal,
    siteOrigin: origin,
    signInUrl: `${origin}/${id}/app/user/login`,
    pageUrl: `${origin}/${id}/app/pathfinder`,
    available: true,
    unavailableReason: null,
  };
}

async function askedOn(sites: SiteResponse[]): Promise<string[]> {
  const asked: string[] = [];
  server.use(
    http.get(`${RUNS_URL}/words`, () => HttpResponse.json(served)),
    http.get(RUNS_URL, ({ request }) => {
      asked.push(request.url);
      return HttpResponse.json([]);
    }),
  );
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryDefaults(sitesOptions().queryKey, { staleTime: Infinity });
  queryClient.setQueryData(sitesOptions().queryKey, sites);
  render(<Page />, { wrapper: Wrapper });
  await screen.findByText(/^No audits/);
  return asked;
}

describe("the audits page", () => {
  it("asks for the locked site's audits on a component site's website", async () => {
    expect(
      await askedOn([
        site("veupathdb", "https://muharram.veupathdb.org", true),
        site("toxodb", window.location.origin),
      ]),
    ).toEqual([`${RUNS_URL}?siteId=toxodb`]);
    expect(
      screen.getByText(
        "No audits on ToxoDB yet. Ask the audit assistant in a conversation to audit a genome.",
      ),
    ).toBeInTheDocument();
  });

  it("asks for every site's audits on the portal's website", async () => {
    expect(
      await askedOn([
        site("veupathdb", window.location.origin, true),
        site("toxodb", "https://muharram.toxodb.org"),
      ]),
    ).toEqual([RUNS_URL]);
    expect(
      screen.getByText(
        "No audits yet. Ask the audit assistant in a conversation to audit a genome.",
      ),
    ).toBeInTheDocument();
  });
});
