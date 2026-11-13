import { describe, expect, it } from "vitest";
import type { SiteResponse } from "@strategist/shared";

import { otherSiteExperiments, placeExperiment } from "./otherSites";

const OWN = [
  { name: "GenesByRNASeqEvidence", displayName: "RNA-Seq evidence" },
  { name: "GenesByText", displayName: "Text search" },
];

const TOXO = {
  site: "toxodb",
  datasetId: "DS_0a1b2c",
  similarity: 0.71,
  line: "Heat shock time course in tachyzoites (RNA-Seq)",
};

const CRYPTO = {
  site: "cryptodb",
  datasetId: "DS_9f8e7d",
  similarity: 0.64,
  line: "Oocyst stress response (microarray)",
};

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

describe("otherSiteExperiments", () => {
  it("reads each experiment of the otherSites entry the answer ends with", () => {
    expect(
      otherSiteExperiments([
        ...OWN,
        {
          otherSites: {
            note: "Experiments on other VEuPathDB sites.",
            experiments: [TOXO, CRYPTO],
          },
        },
      ]),
    ).toEqual([
      { site: "toxodb", datasetId: "DS_0a1b2c", line: TOXO.line },
      { site: "cryptodb", datasetId: "DS_9f8e7d", line: CRYPTO.line },
    ]);
  });

  it("reads none from an answer with no otherSites entry", () => {
    expect(otherSiteExperiments(OWN)).toEqual([]);
  });

  it("reads none from an output that is not an answer list", () => {
    expect(otherSiteExperiments({ count: 6 })).toEqual([]);
    expect(otherSiteExperiments(null)).toEqual([]);
  });
});

describe("placeExperiment", () => {
  it("names the site and links the dataset record page on a site the app holds", () => {
    expect(placeExperiment(TOXO, [TOXODB])).toEqual({
      siteName: "ToxoDB (Toxoplasma)",
      recordUrl: "https://qa.toxodb.org/toxo.qa/app/record/dataset/DS_0a1b2c",
    });
  });

  it("names a site the app does not hold by its id, with no link", () => {
    expect(placeExperiment(CRYPTO, [TOXODB])).toEqual({
      siteName: "cryptodb",
      recordUrl: null,
    });
  });
});
