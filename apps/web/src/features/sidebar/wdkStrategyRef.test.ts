import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@pathfinder/shared";

import { readWdkStrategyEntry } from "./wdkStrategyRef";

function site(id: string, baseUrl: string): SiteResponse {
  return {
    id,
    name: id,
    displayName: id,
    baseUrl,
    projectId: id,
    isPortal: id === "veupathdb",
    available: true,
    unavailableReason: null,
  };
}

const SITES: SiteResponse[] = [
  site("veupathdb", "https://veupathdb.org/veupathdb/service"),
  site("plasmodb", "https://plasmodb.org/plasmo/service"),
  site("toxodb", "https://toxodb.org/toxo/service"),
];

function read(entry: string) {
  return readWdkStrategyEntry(entry, "plasmodb", SITES);
}

describe("readWdkStrategyEntry", () => {
  it("reads a bare strategy id as this site's", () => {
    expect(read("214626640")).toEqual({ kind: "thisSite", wdkStrategyId: 214626640 });
  });

  it("trims surrounding whitespace", () => {
    expect(read("  214626640\n")).toEqual({
      kind: "thisSite",
      wdkStrategyId: 214626640,
    });
  });

  it("reads a link whose host is this site", () => {
    expect(
      read("https://plasmodb.org/plasmo/app/workspace/strategies/214626640"),
    ).toEqual({ kind: "thisSite", wdkStrategyId: 214626640 });
  });

  it("reads a link that names a step after the strategy", () => {
    expect(
      read("https://plasmodb.org/plasmo/app/workspace/strategies/214626640/981234"),
    ).toEqual({ kind: "thisSite", wdkStrategyId: 214626640 });
  });

  it("names the other site a link belongs to", () => {
    expect(read("https://toxodb.org/toxo/app/workspace/strategies/330528343")).toEqual({
      kind: "otherSite",
      host: "toxodb.org",
      siteId: "toxodb",
    });
  });

  it("names the other site for a link with no scheme", () => {
    expect(read("toxodb.org/toxo/app/workspace/strategies/330528343")).toEqual({
      kind: "otherSite",
      host: "toxodb.org",
      siteId: "toxodb",
    });
  });

  it("reads the portal as its own site", () => {
    expect(read("https://veupathdb.org/veupathdb/app/workspace/strategies/12")).toEqual(
      { kind: "otherSite", host: "veupathdb.org", siteId: "veupathdb" },
    );
  });

  it("ignores case and a www prefix in the host", () => {
    expect(read("https://WWW.PlasmoDB.org/plasmo/app/workspace/strategies/7")).toEqual({
      kind: "thisSite",
      wdkStrategyId: 7,
    });
  });

  it("names no site for a host the api does not serve", () => {
    expect(read("https://beta.plasmodb.org/plasmo/app/workspace/strategies/7")).toEqual(
      {
        kind: "otherSite",
        host: "beta.plasmodb.org",
        siteId: null,
      },
    );
  });

  it("reads a path with no host as this site's", () => {
    expect(read("/plasmo/app/workspace/strategies/7")).toEqual({
      kind: "thisSite",
      wdkStrategyId: 7,
    });
  });

  it("rejects text that names no strategy", () => {
    expect(read("kinase sweep")).toEqual({ kind: "unreadable" });
  });

  it("rejects an empty entry", () => {
    expect(read("   ")).toEqual({ kind: "unreadable" });
  });

  it("rejects zero and negative ids", () => {
    expect(read("0")).toEqual({ kind: "unreadable" });
    expect(read("-5")).toEqual({ kind: "unreadable" });
  });

  it("rejects a site URL that names no strategy", () => {
    expect(read("https://plasmodb.org/plasmo/app/workspace")).toEqual({
      kind: "unreadable",
    });
  });
});
