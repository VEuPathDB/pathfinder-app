// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { authStatusOptions } from "@/lib/api/veupathdb-auth";
import { geneSetsListOptions } from "@/features/workbench/api/geneSets";
import { createTestWrapper } from "@/lib/query/testing";
import { useSessionStore } from "@/state/useSessionStore";
import { WorkbenchSidebar } from "./WorkbenchSidebar";

const SITE = "plasmodb";

function draw(signedIn: boolean) {
  useSessionStore.setState({ selectedSite: SITE });
  const { queryClient, Wrapper } = createTestWrapper();
  queryClient.setQueryData(authStatusOptions(SITE).queryKey, {
    signedIn,
    name: "Researcher",
    email: "researcher@upenn.edu",
  });
  if (signedIn) {
    queryClient.setQueryData(geneSetsListOptions(SITE).queryKey, []);
  }
  return render(
    <Wrapper>
      <WorkbenchSidebar />
    </Wrapper>,
  );
}

afterEach(cleanup);

describe("WorkbenchSidebar with no gene sets on screen", () => {
  it("asks a signed-out reader to sign in instead of claiming they have none", () => {
    draw(false);

    expect(
      screen.getByText("Sign in to VEuPathDB to see your gene sets."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No gene sets yet/)).not.toBeInTheDocument();
  });

  it("says the library is empty once the signed-in read answered", () => {
    draw(true);

    expect(screen.getByText(/No gene sets yet/)).toBeInTheDocument();
  });
});
